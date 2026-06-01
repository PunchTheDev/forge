"""
Resource-limit enforcement for agent execution.
Runs the agent's generate() in a forked subprocess with CPU time caps.

Why temp file instead of Queue for STEP bytes:
  multiprocessing.Queue uses a pipe internally. Linux pipe buffer = 64KB.
  A STEP file can be 200-500 KB. If the subprocess calls queue.put(large_bytes)
  while the parent is blocking on proc.join(), neither can make progress:
  the subprocess blocks on the full pipe; the parent blocks on join. Deadlock.
  Fix: write STEP bytes to a temp file; the queue only carries small error strings.

Why RLIMIT_AS is NOT set:
  OCP/OpenCASCADE maps large amounts of virtual memory via shared libraries
  (often >10 GB of address space) even when actual RSS is well under 1 GB.
  Setting RLIMIT_AS kills OCP agents before they can run. Container-level
  memory limits (Docker --memory flag) enforce actual RAM budgets instead.

Performance note: call preload_ocp() in the parent process before run_agent()
  so that forked workers inherit already-loaded OCP modules at zero import cost.
"""

from __future__ import annotations

import importlib.util
import json
import os
import resource
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


# Wall-clock timeout. 180s gives plenty of headroom for OCP geometry ops on CI.
TIMEOUT_SECONDS = 180

# Actual CPU time cap inside the subprocess.
CPU_SECONDS = 150


@dataclass
class AgentResult:
    success: bool
    step_bytes: bytes = b""
    elapsed_seconds: float = 0.0
    error: str = ""


def preload_ocp() -> None:
    """
    Pre-import and warm-up heavy OCP modules in the current (parent) process.

    On Linux, multiprocessing uses fork() by default. Forked children
    inherit already-loaded .so libraries and Python module objects (via
    sys.modules), so OCP import is effectively free in the worker.
    Safe to call multiple times (imports are no-ops once cached).
    """
    try:
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse  # noqa: F401
        from OCP.BRepPrimAPI import (  # noqa: F401
            BRepPrimAPI_MakeBox,
            BRepPrimAPI_MakeCylinder,
        )
        from OCP.Interface import Interface_Static  # noqa: F401
        from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer  # noqa: F401
        from OCP.TopoDS import TopoDS_Compound  # noqa: F401
        from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt  # noqa: F401
    except ImportError:
        pass  # OCP not installed; agents that need it will fail naturally


def run_agent(agent_path: str, spec: dict) -> AgentResult:
    """
    Execute agent_path::generate(spec) in a forked subprocess with resource limits.

    STEP bytes are transferred via a temp file to avoid multiprocessing pipe
    deadlocks (queue.put blocks when the pipe buffer fills with large payloads).
    Error messages use the queue (always small strings).

    Call preload_ocp() before this to amortise OCP import cost across all evals.
    """
    import multiprocessing

    spec_json = json.dumps(spec)
    error_queue: multiprocessing.Queue = multiprocessing.Queue()

    # Temp file for STEP bytes — avoids pipe buffer deadlock
    result_fd, result_path = tempfile.mkstemp(suffix=".step")
    os.close(result_fd)
    # Remove it so the worker can create it only on success
    os.unlink(result_path)

    proc = multiprocessing.Process(
        target=_agent_worker,
        args=(agent_path, spec_json, error_queue, result_path),
        daemon=True,
    )

    t0 = time.monotonic()
    proc.start()
    proc.join(timeout=TIMEOUT_SECONDS)
    elapsed = time.monotonic() - t0

    if proc.is_alive():
        proc.kill()
        proc.join()
        _try_unlink(result_path)
        return AgentResult(
            success=False,
            elapsed_seconds=elapsed,
            error=f"Agent timed out ({TIMEOUT_SECONDS}s wall-clock limit)",
        )

    if proc.exitcode != 0:
        err = "Agent process crashed"
        if not error_queue.empty():
            err = error_queue.get_nowait()
        _try_unlink(result_path)
        return AgentResult(success=False, elapsed_seconds=elapsed, error=err)

    if not os.path.exists(result_path):
        err = "Agent returned no output"
        if not error_queue.empty():
            err = error_queue.get_nowait()
        return AgentResult(success=False, elapsed_seconds=elapsed, error=err)

    try:
        with open(result_path, "rb") as f:
            step_bytes = f.read()
    except Exception as e:
        return AgentResult(
            success=False, elapsed_seconds=elapsed, error=f"Could not read result file: {e}"
        )
    finally:
        _try_unlink(result_path)

    return AgentResult(success=True, step_bytes=step_bytes, elapsed_seconds=elapsed)


def _agent_worker(
    agent_path: str,
    spec_json: str,
    error_queue,
    result_path: str,
) -> None:
    """
    Runs inside the forked subprocess.
    Suppresses C-level stdout to prevent OCC/STEP writer messages from leaking
    into the parent process's stdout (which carries the JSON result).
    """
    # Redirect fd 1 to /dev/null so OCC progress prints don't pollute JSON output.
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_stdout_fd = os.dup(1)
    os.dup2(devnull_fd, 1)
    os.close(devnull_fd)

    _apply_rlimits()

    try:
        spec = json.loads(spec_json)

        sys.path.insert(0, str(Path(agent_path).parent))
        mod_name = Path(agent_path).stem

        loader_spec = importlib.util.spec_from_file_location(mod_name, agent_path)
        mod = importlib.util.module_from_spec(loader_spec)
        loader_spec.loader.exec_module(mod)

        step_bytes = mod.generate(spec)

        if not isinstance(step_bytes, bytes):
            error_queue.put("generate() must return bytes (STEP file content)")
            return

        # Write to temp file — avoids pipe deadlock for large payloads
        with open(result_path, "wb") as f:
            f.write(step_bytes)

    except Exception as e:
        error_queue.put(f"{type(e).__name__}: {e}")
    finally:
        os.dup2(saved_stdout_fd, 1)
        os.close(saved_stdout_fd)


def _apply_rlimits() -> None:
    """Apply CPU time limit to the current process.

    RLIMIT_AS is intentionally omitted — see module docstring.
    """
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS + 5))
    except (ValueError, resource.error):
        pass


def _try_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
