"""
Verify OCP can be imported AND used for BRep ops in a subprocess.

Matches the exact subprocess.Popen params from sandbox.run_agent():
  stdout=DEVNULL, stderr=PIPE, cwd=/forge

Called from eval.yml after docker build. Exits 0 if OCP works, 1 if not.
"""

import subprocess
import sys


def run_check(label: str, code: str) -> bool:
    result = subprocess.run(
        [sys.executable, "-c", code],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        cwd="/forge",
        timeout=60,
    )
    stderr_out = result.stderr.decode("utf-8", errors="replace").strip()
    print(f"[{label}] returncode={result.returncode} stderr={stderr_out!r}")
    if result.returncode != 0:
        print(f"FAIL: {label}")
        return False
    return True


ok = True

# Step 1: basic import
ok &= run_check("import", (
    "from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse; "
    "from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox; "
    "from OCP.gp import gp_Pnt; "
    "import sys; sys.stderr.write('imports OK\\n')"
))

# Step 2: actually build a shape (exercises BRep kernel, not just dynamic linker)
ok &= run_check("makeBox", (
    "from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox; "
    "from OCP.gp import gp_Pnt; "
    "s = BRepPrimAPI_MakeBox(gp_Pnt(0,0,0), gp_Pnt(10,10,10)).Shape(); "
    "import sys; sys.stderr.write('MakeBox OK\\n')"
))

# Step 3: boolean Fuse (uses BOPAlgo — the most crash-prone path)
ok &= run_check("fuse", (
    "from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox; "
    "from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse; "
    "from OCP.gp import gp_Pnt; "
    "a = BRepPrimAPI_MakeBox(gp_Pnt(0,0,0), gp_Pnt(10,10,10)).Shape(); "
    "b = BRepPrimAPI_MakeBox(gp_Pnt(5,5,5), gp_Pnt(15,15,15)).Shape(); "
    "f = BRepAlgoAPI_Fuse(a, b); f.Build(); _ = f.Shape(); "
    "import sys; sys.stderr.write('Fuse OK\\n')"
))

# Step 4: boolean Cut
ok &= run_check("cut", (
    "from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder; "
    "from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut; "
    "from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt; "
    "box = BRepPrimAPI_MakeBox(gp_Pnt(0,0,0), gp_Pnt(20,20,20)).Shape(); "
    "ax = gp_Ax2(gp_Pnt(10,10,-1), gp_Dir(0,0,1)); "
    "cyl = BRepPrimAPI_MakeCylinder(ax, 3.25, 22).Shape(); "
    "c = BRepAlgoAPI_Cut(box, cyl); c.Build(); _ = c.Shape(); "
    "import sys; sys.stderr.write('Cut OK\\n')"
))

if not ok:
    sys.exit(1)
print("PASS: all OCP subprocess checks OK")
