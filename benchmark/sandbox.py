"""
Resource-limit enforcement for agent execution.
Runs the agent's generate() in a subprocess with CPU time caps.

Note: RLIMIT_AS (virtual address space) is intentionally NOT set here.
OCP/OpenCASCADE maps large amounts of virtual memory via shared libraries
(often >10 GB of address space) even when actual RSS is well under 1 GB.
Setting RLIMIT_AS kills OCP agents before they can run. Container-level
memory limits (Docker --memory flag) enforce actual RAM budgets instead.
"""

from __future__ import annotations

import importlib.util
import json
import resource
import sys
import time
from dataclasses import dataclass
from pathlib import Path


# Wall-clock timeout: 120s to give OCP time to load and run.
# RLIMIT_CPU (actual CPU time) is set to 90s inside the subprocess.
TIMEOUT_SECONDS = 120
CPU_SECONDS = 90


@dataclass
class AgentResult:
    success: bool
    step_bytes: bytes = b""
    elapsed_seconds: float = 0.0
    error: str = ""


def run_agent(agent_path: str, spec: dict) -> AgentResult:
    """
    Execute agent_path::generate(spec) in a subprocess with resource limits.
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
        return AgentResult(success=False, elapsed_seconds=elapsed, error=f"Agent timed out ({TIMEOUT_SECONDS}s wall-clock limit)")

    if proc.exitcode != 0:
        err = "Agent process crashed"
        if not result_queue.empty():
            err = result_queue.get_nowait()
        return AgentResult(success=False, elapsed_seconds=elapsed, error=err)

    if result_queue.empty():
        return AgentResult(success=False, elapsed_seconds=elapsed, error="Agent returned no output")

    item = result_queue.get_nowait()
    if isinstance(item, str):
        return AgentResult(success=False, elapsed_seconds=elapsed, error=item)

    return AgentResult(success=True, step_bytes=item, elapsed_seconds=elapsed)


def _agent_worker(agent_path: str, spec_json: str, result_queue) -> None:
    """Runs inside the subprocess. Applies rlimits then calls generate()."""
    _apply_rlimits()

    try:
        spec = json.loads(spec_json)
        spec_obj = Path(agent_path).parent

        sys.path.insert(0, str(spec_obj))
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


def _apply_rlimits() -> None:
    """Apply CPU time limit to the current process.

    RLIMIT_AS is intentionally omitted — see module docstring.
    """
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS + 5))
    except (ValueError, resource.error):
        pass
