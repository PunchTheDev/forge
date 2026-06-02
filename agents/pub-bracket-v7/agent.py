"""
pub-bracket-v7: Wide hollow-box arm for pub_003_medium (PETG, 53 kg @ 110 mm).

Root cause of v3 failure: arm at y=43.6mm offsets from both bolt columns (y=0,
y=62.4mm), so all load transfers through the plate in bending. Wider arm made it
worse (more bending moment arm). Fix: arm spans full bolt_y_span — sides land
directly on bolt columns, eliminating plate bending.

Design:
  fw     = bolt_y_span = 62.4mm  (arm spans y=0..62.4mm, sides ARE the bolt columns)
  t_wall = 1.6mm  (thicker than min_wall for PETG stress — computed below)
  h      = 53mm   |53 - lp[2]| = |53 - 39.6| = 13.4mm < 15mm ✓
  arm_len = lp[0] + 1.0 = 111.2mm

Stress (bending about y-axis, load in -z):
  M = 517.31 × 2.0 × 110.2 = 114,015 N·mm
  I_outer = 62.4 × 53³/12 = 775,019 mm⁴
  I_inner = 59.2 × 49.8³/12 = 609,005 mm⁴
  I_net   = 166,014 mm⁴,  c = 26.5mm
  σ = 114,015 × 26.5 / 166,014 = 18.2 MPa < 20 MPa allowable ✓

Mass estimate (PETG 1.27e-3 g/mm³):
  Arm outer: 62.4 × 53 × 111.2 = 367,737 mm³
  Arm inner: 59.2 × 49.8 × 109.6 = 323,132 mm³  (void starts at x=plate_t)
  Arm net:   44,605 mm³ → 56.6g
  Plate net: ~9.8g
  Total:     ~66g (vs baseline 216.4g, −69%)
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v7 (wide hollow box, PETG pub_003)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d = c["bolt_diameter_clearance_mm"]
    lp = c["load_point_mm"]
    min_wall = c.get("min_wall_thickness_mm", 1.2)

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    bolt_r = bolt_d / 2.0

    t_wall = 1.6             # thicker walls: PETG needs more section modulus than Al
    plate_t = min_wall        # 1.2mm
    margin = bolt_r + plate_t

    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    arm_y0 = float(min(by_coords))
    arm_y1 = float(max(by_coords))
    h = 53.0           # |53 - 39.6| = 13.4mm < 15mm load tolerance ✓
    arm_len = lp[0] + 1.0

    # Wide hollow box: sides at y=arm_y0 and y=arm_y1 (the bolt column lines)
    outer_arm = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, arm_y0, 0.0),
        gp_Pnt(arm_len, arm_y1, h),
    ).Shape()

    inner_void = BRepPrimAPI_MakeBox(
        gp_Pnt(plate_t, arm_y0 + t_wall, t_wall),
        gp_Pnt(arm_len, arm_y1 - t_wall, h - t_wall),
    ).Shape()

    cut1 = BRepAlgoAPI_Cut(outer_arm, inner_void)
    cut1.Build()
    arm_shape = cut1.Shape()

    # Mounting plate (extends beyond arm to cover outer bolt margins)
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    fuse1 = BRepAlgoAPI_Fuse(arm_shape, plate)
    fuse1.Build()
    shape = fuse1.Shape()

    # Bolt holes
    for bby, bbz in bolt_pattern:
        axis = gp_Ax2(gp_Pnt(-1.0, bby, bbz), gp_Dir(1.0, 0.0, 0.0))
        hole = BRepPrimAPI_MakeCylinder(axis, bolt_r, plate_t + 2.0).Shape()
        cut_op = BRepAlgoAPI_Cut(shape, hole)
        cut_op.Build()
        shape = cut_op.Shape()

    writer = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
    writer.Transfer(shape, STEPControl_AsIs)

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
        path = f.name
    try:
        writer.Write(path)
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.unlink(path)
