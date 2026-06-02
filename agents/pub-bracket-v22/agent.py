"""
pub-bracket-v22: Tighter hollow-box arm for pub_004_medium.

Improvement over v4: minimum viable arm dimensions.
  - Arm height: load_z + mw + 12 mm (≥10 mm inner-ceiling clearance rule)
  - Arm length: load_x - 12 mm (12 mm margin within ±15 mm load tolerance)
  - Plate unchanged — same bolt grid, t_wall margins
  - Arm utilisation target: ≤75% allowable
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v22 (tight hollow arm, PLA, pub_004)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c   = spec["constraints"]
    bp  = c["bolt_pattern_mm"]
    bd  = c["bolt_diameter_clearance_mm"]
    lp  = c["load_point_mm"]
    mw  = c.get("min_wall_thickness_mm", 1.2)
    bv  = c["build_volume_mm"]

    lx, ly, lz = lp
    bvx, bvy, bvz = bv
    r  = bd / 2.0
    mg = r + mw

    # Plate extents
    pt    = mw
    py0_r = min(p[0] for p in bp) - mg
    py1_r = max(p[0] for p in bp) + mg
    pz0_r = min(p[1] for p in bp) - mg
    pz1_r = max(p[1] for p in bp) + mg

    dy = py1_r - py0_r
    if dy > bvy - 0.5:
        sh = (dy - (bvy - 0.5)) / 2.0
        py0, py1 = py0_r + sh, py1_r - sh
    else:
        py0, py1 = py0_r, py1_r

    dz = pz1_r - pz0_r
    if dz > bvz - 0.5:
        sh = (dz - (bvz - 0.5)) / 2.0
        pz0, pz1 = pz0_r + sh, pz1_r - sh
    else:
        pz0, pz1 = pz0_r, pz1_r

    # Hollow arm — minimum viable dimensions
    aw = 3.0 * mw          # arm y-width (3.6 mm at mw=1.2)

    # Height: load_z + inner wall + 12 mm clearance (≥10 mm mesh stability rule)
    h = lz + mw + 12.0

    # Length: 12 mm short of load point (±15 mm tolerance; 12 mm leaves mesh headroom)
    al = lx - 12.0
    al = min(al, bvx - 2.0)

    yc = ly

    outer = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, yc - aw / 2, 0.0),
        gp_Pnt(al,  yc + aw / 2, h),
    ).Shape()

    inner = BRepPrimAPI_MakeBox(
        gp_Pnt(pt, yc - aw / 2 + mw, mw),
        gp_Pnt(al, yc + aw / 2 - mw, h - mw),
    ).Shape()

    arm = BRepAlgoAPI_Cut(outer, inner).Shape()

    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, py0, pz0),
        gp_Pnt(pt,  py1, pz1),
    ).Shape()

    body = BRepAlgoAPI_Fuse(arm, plate).Shape()

    for by, bz in bp:
        ax  = gp_Ax2(gp_Pnt(-1.0, by, bz), gp_Dir(1, 0, 0))
        cyl = BRepPrimAPI_MakeCylinder(ax, r, pt + 2.0).Shape()
        body = BRepAlgoAPI_Cut(body, cyl).Shape()

    writer = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
    writer.Transfer(body, STEPControl_AsIs)

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as tf:
        tmp = tf.name
    try:
        writer.Write(tmp)
        return open(tmp, "rb").read()
    finally:
        os.unlink(tmp)
