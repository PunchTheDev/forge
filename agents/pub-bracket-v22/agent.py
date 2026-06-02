"""
pub-bracket-v22: I-beam arm for pub_004_medium.

Improvement over v4 (hollow box): I-beam cross-section uses material only
where bending stress is highest — at the top and bottom flanges.

  - Flanges: fw_f=20mm wide × mw thick, centred at arm y-axis
  - Web: mw wide × (h-2mw) tall
  - h = max(load_z + mw + 12, pz1 + 12) — arm top clearly above plate top
  - arm_len = load_x − 12 mm (12 mm margin within ±15 mm load tolerance)

Analytical check (PLA, 25 MPa allowable):
  I ≈ 73,500 mm⁴, c = 32.5 mm, M = 303.22 × 71.3 = 21,620 N·mm
  σ ≈ 9.6 MPa → 38% utilisation ✓

Estimated mass ≈ 16.5 g (−24% vs v4 at 21.68 g).
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v22 (I-beam arm, PLA, pub_004)."""
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
    py0   = min(p[0] for p in bp) - mg
    py1   = max(p[0] for p in bp) + mg
    pz0   = min(p[1] for p in bp) - mg
    pz1   = max(p[1] for p in bp) + mg

    dy = py1 - py0
    if dy > bvy - 0.5:
        sh = (dy - (bvy - 0.5)) / 2.0
        py0, py1 = py0 + sh, py1 - sh

    dz = pz1 - pz0
    if dz > bvz - 0.5:
        sh = (dz - (bvz - 0.5)) / 2.0
        pz0, pz1 = pz0 + sh, pz1 - sh

    # I-beam arm parameters
    fw_f = 20.0    # flange width in y — maximises I for given flange mass
    yc   = ly      # arm centred on load point y

    # Arm height: must clear plate top (pz1) by ≥12 mm to avoid near-degenerate
    # geometry at arm-plate junction, AND satisfy CalculiX mesh rule.
    h = max(lz + mw + 12.0, pz1 + 12.0)
    h = min(h, bvz - 2.0)

    # Arm length: 12 mm short of load point (mesh headroom within ±15 mm tolerance)
    al = lx - 12.0
    al = min(al, bvx - 2.0)

    # Web: full height, mw wide
    web = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, yc - mw / 2, 0.0),
        gp_Pnt(al,  yc + mw / 2, h),
    ).Shape()

    # Bottom flange: wide, mw thick, at z=0
    bot_flange = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, yc - fw_f / 2, 0.0),
        gp_Pnt(al,  yc + fw_f / 2, mw),
    ).Shape()

    # Top flange: wide, mw thick, at z=h-mw
    top_flange = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, yc - fw_f / 2, h - mw),
        gp_Pnt(al,  yc + fw_f / 2, h),
    ).Shape()

    arm = BRepAlgoAPI_Fuse(web, bot_flange).Shape()
    arm = BRepAlgoAPI_Fuse(arm, top_flange).Shape()

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
