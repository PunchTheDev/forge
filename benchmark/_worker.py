"""
Standalone subprocess worker for agent evaluation.

Called by sandbox.run_agent() via subprocess.Popen. Runs in a fresh Python
interpreter so it is immune to multiprocessing fork/semaphore issues.

Exit codes:
  0  — STEP bytes written to --out path
  1  — agent raised an exception (message on stderr)
  2  — generate() returned non-bytes (message on stderr)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import resource
import sys
from pathlib import Path

CPU_SECONDS = 150


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    # Lower CPU time limit (privilege-free — we are only lowering it).
    try:
        resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS + 5))
    except (ValueError, OSError):
        pass

    spec = json.loads(Path(args.spec).read_text())

    sys.path.insert(0, str(Path(args.agent).parent))
    loader_spec = importlib.util.spec_from_file_location(Path(args.agent).stem, args.agent)
    mod = importlib.util.module_from_spec(loader_spec)

    try:
        loader_spec.loader.exec_module(mod)
        step_bytes = mod.generate(spec)
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(step_bytes, bytes):
        print("generate() must return bytes (STEP file content)", file=sys.stderr)
        sys.exit(2)

    Path(args.out).write_bytes(step_bytes)


if __name__ == "__main__":
    main()
