"""
pub-bracket-v5: Parametric hollow-box cantilever bracket for pub_005_medium.

Target: PLA (FDM), 48 kg load at ~120 mm arm.
Strategy: maximise arm height within build volume for bending stiffness,
  use minimum hollow-box cross-section (3 × min_wall) to keep mass low.

Geometry:
  - Arm: hollow box, z=0..h, x=0..arm_len, centred on load_y
  - h = min(bvz-5, max(bvz*0.75, lz+16+mw)) — top clear of load zone
  - arm_len = clamp(lx-15 .. lx*0.9, max=bvx-2)
  - Plate: encloses bolt pattern + clearance margin, clipped to bv
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v5 (hollow cantilever, PLA, ~120 mm)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c  = spec["constraints"]
    bp = c["bolt_pattern_mm"]
    bd = c["bolt_diameter_clearance_mm"]
    lp = c["load_point_mm"]
    mw = c.get("min_wall_thickness_mm", 1.2)
    bv = c["build_volume_mm"]

    lx, ly, lz = lp
    bvx, bvy, bvz = bv

    brad = bd / 2.0
    mrg  = brad + mw

    # Plate: minimal bounding box over bolt holes + margin
    pt    = mw
    py0_r = min(p[0] for p in bp) - mrg
    py1_r = max(p[0] for p in bp) + mrg
    pz0_r = min(p[1] for p in bp) - mrg
    pz1_r = max(p[1] for p in bp) + mrg

    yspan = py1_r - py0_r
    if yspan > bvy - 0.5:
        trim = (yspan - (bvy - 0.5)) / 2.0
        py0, py1 = py0_r + trim, py1_r - trim
    else:
        py0, py1 = py0_r, py1_r

    zspan = pz1_r - pz0_r
    if zspan > bvz - 0.5:
        trim = (zspan - (bvz - 0.5)) / 2.0
        pz0, pz1 = pz0_r + trim, pz1_r - trim
    else:
        pz0, pz1 = pz0_r, pz1_r

    # Arm cross-section: 3-wall-wide hollow box
    aw = 3.0 * mw

    # Arm height: tall enough that load zone top is inside arm body, not at tip
    h_min  = lz + 16.0 + mw        # ≥16 mm above load z
    h_want = bvz * 0.75
    h      = min(bvz - 5.0, max(h_want, h_min))

    # Arm length: between (lx-15) and 90% lx, within build volume
    al = min(max(lx - 15.0, lx * 0.90), bvx - 2.0)

    yc = ly

    outer = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, yc - aw / 2, 0.0),
        gp_Pnt(al,  yc + aw / 2, h),
    ).Shape()

    # Hollow interior — open on +x end, walls on remaining five faces
    void = BRepPrimAPI_MakeBox(
        gp_Pnt(pt, yc - aw / 2 + mw, mw),
        gp_Pnt(al, yc + aw / 2 - mw, h - mw),
    ).Shape()

    arm = BRepAlgoAPI_Cut(outer, void).Shape()

    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, py0, pz0),
        gp_Pnt(pt,  py1, pz1),
    ).Shape()

    body = BRepAlgoAPI_Fuse(arm, plate).Shape()

    for by, bz in bp:
        axis = gp_Ax2(gp_Pnt(-1.0, by, bz), gp_Dir(1, 0, 0))
        hole = BRepPrimAPI_MakeCylinder(axis, brad, pt + 2.0).Shape()
        body = BRepAlgoAPI_Cut(body, hole).Shape()

    # STEP output
    wr = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
    wr.Transfer(body, STEPControl_AsIs)

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as fh:
        out = fh.name
    try:
        wr.Write(out)
        return open(out, "rb").read()
    finally:
        os.unlink(out)
