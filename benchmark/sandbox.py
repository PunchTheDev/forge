"""
Resource-limit enforcement for agent execution.
Runs the agent's generate() in a subprocess with CPU time and memory caps.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pickle
import resource
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path


TIMEOUT_SECONDS = 60
MEMORY_LIMIT_BYTES = 4 * 1024 ** 3  # 4 GB


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
        return AgentResult(success=False, elapsed_seconds=elapsed, error="Agent timed out (60s limit)")

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
    """Apply memory and CPU time limits to the current process."""
    try:
        resource.setrlimit(resource.RLIMIT_AS, (MEMORY_LIMIT_BYTES, MEMORY_LIMIT_BYTES))
    except (ValueError, resource.error):
        pass  # Best-effort on platforms that don't support it

    try:
        resource.setrlimit(resource.RLIMIT_CPU, (TIMEOUT_SECONDS, TIMEOUT_SECONDS + 5))
    except (ValueError, resource.error):
        pass
