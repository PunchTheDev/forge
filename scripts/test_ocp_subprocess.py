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

# Step 5: thin-wall geometry like the trim-frame agent (plate 1.2×70×70 + web 1.2mm wide)
# This is the specific geometry that was crashing in eval.
ok &= run_check("thin-fuse", (
    "from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox; "
    "from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse; "
    "from OCP.gp import gp_Pnt; "
    "plate = BRepPrimAPI_MakeBox(gp_Pnt(0,0,0), gp_Pnt(1.2,70,70)).Shape(); "
    "web = BRepPrimAPI_MakeBox(gp_Pnt(0,24.4,0), gp_Pnt(108,25.6,90)).Shape(); "
    "f1 = BRepAlgoAPI_Fuse(plate, web); f1.Build(); "
    "s1 = f1.Shape(); "
    "bot = BRepPrimAPI_MakeBox(gp_Pnt(0,21,0), gp_Pnt(108,29,1.2)).Shape(); "
    "f2 = BRepAlgoAPI_Fuse(s1, bot); f2.Build(); "
    "s2 = f2.Shape(); "
    "import sys; sys.stderr.write('thin-fuse OK\\n')"
))

# Step 6: run the actual trim-frame agent step by step to isolate the crash
_step6_code = r"""
import sys
w = sys.stderr.write
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt
w('step1: imports OK\n')

plate_t=1.2; plate_y=70.0; plate_z=70.0
arm_x=108.0; web_w=1.2; flange_w=8.0; flange_t=1.2; total_h=90.0
y_center=25.0
web_y0=y_center-web_w/2; web_y1=y_center+web_w/2
flange_y0=y_center-flange_w/2; flange_y1=y_center+flange_w/2

plate=BRepPrimAPI_MakeBox(gp_Pnt(0,0,0),gp_Pnt(plate_t,plate_y,plate_z)).Shape()
web=BRepPrimAPI_MakeBox(gp_Pnt(plate_t,web_y0,flange_t),gp_Pnt(arm_x,web_y1,total_h-flange_t)).Shape()
bot=BRepPrimAPI_MakeBox(gp_Pnt(plate_t,flange_y0,0),gp_Pnt(arm_x,flange_y1,flange_t)).Shape()
top=BRepPrimAPI_MakeBox(gp_Pnt(plate_t,flange_y0,total_h-flange_t),gp_Pnt(arm_x,flange_y1,total_h)).Shape()
w('step2: boxes OK\n')

f1=BRepAlgoAPI_Fuse(plate,web); f1.Build(); s1=f1.Shape()
w('step3: fuse1 OK\n')
f2=BRepAlgoAPI_Fuse(s1,bot); f2.Build(); s2=f2.Shape()
w('step4: fuse2 OK\n')
f3=BRepAlgoAPI_Fuse(s2,top); f3.Build(); shape=f3.Shape()
w('step5: fuse3 OK\n')

bolt_pattern=[[0,0],[60,0],[60,60],[0,60]]; bolt_d=6.5
for i,(by,bz) in enumerate(bolt_pattern):
    axis=gp_Ax2(gp_Pnt(-1.0,by,bz),gp_Dir(1.0,0.0,0.0))
    hole=BRepPrimAPI_MakeCylinder(axis,bolt_d/2.0,plate_t+2.0).Shape()
    cop=BRepAlgoAPI_Cut(shape,hole); cop.Build(); shape=cop.Shape()
    w(f'step6.{i}: cut OK\n')

w('step7a: before STEPControl_Writer()\n')
writer=STEPControl_Writer()
w('step7b: before SetCVal_s\n')
Interface_Static.SetCVal_s('write.step.schema','AP203')
w('step7c: before Transfer\n')
writer.Transfer(shape,STEPControl_AsIs)
w('step7d: Transfer OK\n')
import tempfile,os
with tempfile.NamedTemporaryFile(suffix='.step',delete=False) as f: path=f.name
writer.Write(path)
data=open(path,'rb').read(); os.unlink(path)
assert len(data)>100
w(f'step8: Write OK, {len(data)} bytes\n')
"""
ok &= run_check("agent-steps", _step6_code)

if not ok:
    sys.exit(1)
print("PASS: all OCP subprocess checks OK")
