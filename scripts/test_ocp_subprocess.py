"""
Verify OCP can be imported in a subprocess.

Called from eval.yml after docker build to catch SIGSEGV/SIGILL from broken
OCP installs before running the full evaluation.

Exit 0  — OCP works in subprocess.
Exit 1  — subprocess failed (stderr printed above).
"""

import subprocess
import sys

result = subprocess.run(
    [sys.executable, "-c",
     "from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut; print('OCP subprocess OK')"],
    capture_output=True,
    text=True,
    timeout=60,
)
print("stdout:", result.stdout.strip())
if result.stderr.strip():
    print("stderr:", result.stderr.strip())
print("returncode:", result.returncode)
sys.exit(result.returncode)
