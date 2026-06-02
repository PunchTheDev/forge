"""
Resource-limit enforcement for agent execution.

Runs the agent's generate() in a subprocess launched via subprocess.Popen.
Stderr from the child is captured and surfaced in the error message, so CI
comments always show the actual Python exception rather than "process crashed".

Why subprocess instead of multiprocessing:
  The previous multiprocessing.Process approach silently died inside Docker when
  --cap-drop ALL dropped the capability needed to operate POSIX semaphores used
  by multiprocessing.Queue. The child exited with a non-zero code before reaching
  the Python try/except, leaving the error queue empty and the reason opaque.

  subprocess.Popen spawns a fresh interpreter with no semaphore dependency.
  Stderr is piped to the parent so any crash produces a useful error message.

Why RLIMIT_AS is NOT set:
  OCP/OpenCASCADE maps large virtual address ranges via shared libraries
  (often >10 GB VA) even when actual RSS is well under 1 GB.
  Setting RLIMIT_AS kills OCP agents prematurely. Container-level --memory
  caps enforce actual RAM budgets instead.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

# Wall-clock timeout for the agent subprocess.
TIMEOUT_SECONDS = 180


@dataclass
class AgentResult:
    success: bool
    step_bytes: bytes = b""
    elapsed_seconds: float = 0.0
    error: str = ""


def preload_ocp() -> None:
    """
    No-op kept for API compatibility.

    With subprocess-based sandboxing each agent runs in a fresh interpreter,
    so module preloading in the parent has no effect. The function is retained
    so callers do not need updating.
    """


def run_agent(agent_path: str, spec: dict) -> AgentResult:
    """
    Execute agent_path::generate(spec) in a sandboxed subprocess.

    The worker (benchmark/_worker.py) runs in a fresh Python interpreter,
    applies a CPU time limit, loads the agent, calls generate(spec), and
    writes the STEP bytes to a temp file.  The parent reads the STEP bytes,
    applies the wall-clock timeout, and surfaces any stderr output on failure.
    """
    spec_fd, spec_path = tempfile.mkstemp(suffix=".json")
    result_fd, result_path = tempfile.mkstemp(suffix=".step")
    os.close(spec_fd)
    os.close(result_fd)
    # Worker creates result_path only on success; remove the placeholder.
    os.unlink(result_path)

    try:
        with os.fdopen(os.open(spec_path, os.O_WRONLY | os.O_TRUNC), "w") as f:
            json.dump(spec, f)

        worker_module = str(Path(__file__).parent / "_worker.py")
        proc = subprocess.Popen(
            [sys.executable, worker_module,
             "--agent", agent_path,
             "--spec", spec_path,
             "--out", result_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            cwd=str(Path(__file__).parent.parent),
        )

        t0 = time.monotonic()
        try:
            _, stderr_bytes = proc.communicate(timeout=TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            elapsed = time.monotonic() - t0
            _try_unlink(result_path)
            return AgentResult(
                success=False,
                elapsed_seconds=elapsed,
                error=f"Agent timed out ({TIMEOUT_SECONDS}s wall-clock limit)",
            )

        elapsed = time.monotonic() - t0

        if proc.returncode != 0:
            stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
            # Truncate to last 800 chars to keep the CI comment readable.
            err = (stderr_text[-800:]
                   if stderr_text
                   else f"Agent process crashed (exit {proc.returncode}, no stderr)")
            _try_unlink(result_path)
            return AgentResult(success=False, elapsed_seconds=elapsed, error=err)

        if not os.path.exists(result_path):
            stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
            err = f"Agent produced no output. stderr: {stderr_text[-400:]}"
            return AgentResult(success=False, elapsed_seconds=elapsed, error=err)

        try:
            with open(result_path, "rb") as f:
                step_bytes = f.read()
        except Exception as exc:
            return AgentResult(
                success=False,
                elapsed_seconds=elapsed,
                error=f"Could not read result file: {exc}",
            )
        finally:
            _try_unlink(result_path)

        return AgentResult(success=True, step_bytes=step_bytes, elapsed_seconds=elapsed)

    finally:
        _try_unlink(spec_path)


def _try_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
