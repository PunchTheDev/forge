"""
Verify OCP can be imported in a subprocess with the exact same params as sandbox.py.

Called from eval.yml after docker build. Exits 0 if OCP works, 1 if not.
"""

import subprocess
import sys
from pathlib import Path

# Replicate the exact subprocess.Popen call used by sandbox.run_agent().
# stdout=DEVNULL and cwd=/forge are the key differences vs a plain subprocess.run.
result = subprocess.run(
    [sys.executable, "-c",
     "from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut; import sys; sys.stderr.write('OCP subprocess OK\\n')"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.PIPE,
    cwd="/forge",
    timeout=60,
)
stderr_out = result.stderr.decode("utf-8", errors="replace").strip()
print(f"stderr: {stderr_out!r}")
print(f"returncode: {result.returncode}")
if result.returncode != 0:
    print("FAIL: OCP subprocess crashed")
    sys.exit(1)
print("PASS: OCP subprocess OK")
