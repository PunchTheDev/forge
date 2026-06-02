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

_geom_prefix = (
    "from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut,BRepAlgoAPI_Fuse;"
    "from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox,BRepPrimAPI_MakeCylinder;"
    "from OCP.Interface import Interface_Static;"
    "from OCP.STEPControl import STEPControl_AsIs,STEPControl_Writer;"
    "from OCP.gp import gp_Ax2,gp_Dir,gp_Pnt;"
    "import sys,tempfile,os;"
    "plate_t=1.2;arm_x=108.0;web_w=1.2;flange_w=8.0;flange_t=1.2;total_h=90.0;"
    "bolt_d=6.5;bolt_r=bolt_d/2.0;"
    "plate_y0=-4.25;plate_z0=-4.25;plate_y1=70.0;plate_z1=70.0;"
    "y_center=25.0;web_y0=y_center-web_w/2;web_y1=y_center+web_w/2;"
    "flange_y0=y_center-flange_w/2;flange_y1=y_center+flange_w/2;"
    "plate=BRepPrimAPI_MakeBox(gp_Pnt(0,plate_y0,plate_z0),gp_Pnt(plate_t,plate_y1,plate_z1)).Shape();"
    "web=BRepPrimAPI_MakeBox(gp_Pnt(plate_t,web_y0,flange_t),gp_Pnt(arm_x,web_y1,total_h-flange_t)).Shape();"
    "bot=BRepPrimAPI_MakeBox(gp_Pnt(plate_t,flange_y0,0),gp_Pnt(arm_x,flange_y1,flange_t)).Shape();"
    "top=BRepPrimAPI_MakeBox(gp_Pnt(plate_t,flange_y0,total_h-flange_t),gp_Pnt(arm_x,flange_y1,total_h)).Shape();"
    "f1=BRepAlgoAPI_Fuse(plate,web);f1.Build();s1=f1.Shape();"
    "f2=BRepAlgoAPI_Fuse(s1,bot);f2.Build();s2=f2.Shape();"
    "f3=BRepAlgoAPI_Fuse(s2,top);f3.Build();shape=f3.Shape();"
)

def _step_export(shape_expr: str) -> str:
    return (
        f"shape_to_exp=({shape_expr});"
        "wr=STEPControl_Writer();"
        "Interface_Static.SetCVal_s('write.step.schema','AP214IS');"
        "wr.Transfer(shape_to_exp,STEPControl_AsIs);"
        "with tempfile.NamedTemporaryFile(suffix='.step',delete=False) as f: p=f.name;"
        "wr.Write(p);d=open(p,'rb').read();os.unlink(p);"
        "assert len(d)>100;"
        "sys.stderr.write(f'step OK {len(d)} bytes\\n');"
    )

# Bisect: does Transfer crash at fuse1, fuse2, fuse3, or after cuts?
ok &= run_check("step-after-fuse1",  _geom_prefix + _step_export("s1"))
ok &= run_check("step-after-fuse2",  _geom_prefix + _step_export("s2"))
ok &= run_check("step-after-fuse3",  _geom_prefix + _step_export("shape"))

_cuts = (
    "cut_ops=[];"
    "bolt_pattern=[[0,0],[60,0],[60,60],[0,60]];"
    "for by,bz in bolt_pattern:"
    " axis=gp_Ax2(gp_Pnt(-1.0,by,bz),gp_Dir(1.0,0.0,0.0));"
    " hole=BRepPrimAPI_MakeCylinder(axis,bolt_r,plate_t+2.0).Shape();"
    " cop=BRepAlgoAPI_Cut(shape,hole);cop.Build();cut_ops.append(cop);shape=cop.Shape();"
)
ok &= run_check("step-after-4cuts", _geom_prefix + _cuts + _step_export("shape"))

if not ok:
    sys.exit(1)
print("PASS: all OCP subprocess checks OK")
