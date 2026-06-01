"""
Resource-limit enforcement for agent execution.
Runs the agent's generate() in a subprocess with CPU time caps.

Note: RLIMIT_AS (virtual address space) is intentionally NOT set here.
OCP/OpenCASCADE maps large amounts of virtual memory via shared libraries
(often >10 GB of address space) even when actual RSS is well under 1 GB.
Setting RLIMIT_AS kills OCP agents before they can run. Container-level
memory limits (Docker --memory flag) enforce actual RAM budgets instead.

Performance note: OCP Python bindings are large (~60-90s cold import).
Call preload_ocp() in the parent process before run_agent() so that
forked workers inherit already-loaded OCP modules at zero cost.
"""

from __future__ import annotations

import importlib.util
import json
import os
import resource
import sys
import time
from dataclasses import dataclass
from pathlib import Path


# Wall-clock timeout. OCP BRep operations on CI runners can be slow;
# set high enough that legitimate designs complete even on cold starts.
TIMEOUT_SECONDS = 300

# Actual CPU time cap inside the subprocess.
CPU_SECONDS = 270


@dataclass
class AgentResult:
    success: bool
    step_bytes: bytes = b""
    elapsed_seconds: float = 0.0
    error: str = ""


def preload_ocp() -> None:
    """
    Pre-import heavy OCP modules in the current (parent) process.

    On Linux, multiprocessing uses fork() by default. Forked children
    inherit already-loaded .so libraries and Python module objects, so
    OCP import is effectively free in the worker when this is called first.
    Safe to call multiple times (imports are no-ops once cached).
    """
    try:
        import OCP.BRepAlgoAPI  # noqa: F401
        import OCP.BRepPrimAPI  # noqa: F401
        import OCP.Interface    # noqa: F401
        import OCP.STEPControl  # noqa: F401
        import OCP.TopoDS       # noqa: F401
        import OCP.gp           # noqa: F401
    except ImportError:
        pass  # OCP not installed; agents that need it will fail naturally


def run_agent(agent_path: str, spec: dict) -> AgentResult:
    """
    Execute agent_path::generate(spec) in a forked subprocess with resource limits.
    Call preload_ocp() before this to amortise OCP import cost across all evals.
    Returns AgentResult containing STEP bytes on success.
    """
    import multiprocessing

    spec_json = json.dumps(spec)
    result_queue: multiprocessing.Queue = multiprocessing.Queue()

    proc = multiprocessing.Process(
        target=_agent_worker,
        args=(agent_path, spec_json, result_queue),
        daemon=True,
    )

    t0 = time.monotonic()
    proc.start()
    proc.join(timeout=TIMEOUT_SECONDS)
    elapsed = time.monotonic() - t0

    if proc.is_alive():
        proc.kill()
        proc.join()
        return AgentResult(
            success=False,
            elapsed_seconds=elapsed,
            error=f"Agent timed out ({TIMEOUT_SECONDS}s wall-clock limit)",
        )

    if proc.exitcode != 0:
        err = "Agent process crashed"
        if not result_queue.empty():
            err = result_queue.get_nowait()
        return AgentResult(success=False, elapsed_seconds=elapsed, error=err)

    if result_queue.empty():
        return AgentResult(
            success=False, elapsed_seconds=elapsed, error="Agent returned no output"
        )

    item = result_queue.get_nowait()
    if isinstance(item, str):
        return AgentResult(success=False, elapsed_seconds=elapsed, error=item)

    return AgentResult(success=True, step_bytes=item, elapsed_seconds=elapsed)


def _agent_worker(agent_path: str, spec_json: str, result_queue) -> None:
    """Runs inside the forked subprocess. Suppresses C-level stdout to prevent
    OCC/STEP writer progress messages from leaking into the parent's stdout."""
    # Redirect fd 1 to /dev/null so OCC prints don't pollute evaluate.py's JSON output.
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    saved_stdout_fd = os.dup(1)
    os.dup2(devnull_fd, 1)
    os.close(devnull_fd)

    _apply_rlimits()

    try:
        spec = json.loads(spec_json)

        sys.path.insert(0, str(Path(agent_path).parent))
        mod_name = Path(agent_path).stem

        spec_full = importlib.util.spec_from_file_location(mod_name, agent_path)
        mod = importlib.util.module_from_spec(spec_full)
        spec_full.loader.exec_module(mod)

        step_bytes = mod.generate(spec)

        if not isinstance(step_bytes, bytes):
            result_queue.put("generate() must return bytes (STEP file content)")
            return

        result_queue.put(step_bytes)

    except Exception as e:
        result_queue.put(f"{type(e).__name__}: {e}")
    finally:
        # Restore stdout so any post-worker logging still works
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
