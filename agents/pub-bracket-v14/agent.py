"""
pub-bracket-v14: Reduced-height wide hollow arm for pub_003_medium (PETG).

Frame plate (v8) failed with 73.1 MPa (3.65× over allowable): arm top at z=40mm
is below the top bolt row at z=62.4mm, so thin perimeter strips (4.45mm × 1.2mm)
carry the full moment to the upper bolts — catastrophic stress concentration.
Frame plate is incompatible with pub_003 geometry. Back to solid plate + h reduction.

Scaling from v7 (h=53mm, FEA=11.33 MPa, 56.6% of 20 MPa):
  h=45mm: I_net ratio × correction → predicted ~14.9 MPa (74.5% util) — safe
  h=45 satisfies |45 − lp[2]=39.6| = 5.4 mm < 15 mm load-node tolerance ✓

Design:
  fw      = bolt_y_span = 62.4 mm  (sides at bolt columns y=0, y=62.4)
  t_wall  = 1.5 mm  (reduced from 1.6 mm)
  h       = 45 mm
  arm_len = lp[0] + 1 mm
  plate   = solid, min_wall thick (same as v7)

Stress analysis (scaling from v7 FEA):
  I_net(v7, h=53, t=1.6) = 165,794 mm⁴,  c_v7 = 26.5 mm
  I_outer(h=45)  = 62.4 × 45³ / 12 = 473,850 mm⁴
  I_inner(h=45)  = 59.4 × 42³ / 12 = 366,735 mm⁴  (fw_i=62.4−2×1.5=59.4, h_i=45−3=42)
  I_net(v14)     = 107,115 mm⁴,  c = 22.5 mm
  Stress ratio   = (22.5/107,115) / (26.5/165,794) = 1.314
  FEA predicted  = 11.33 × 1.314 ≈ 14.9 MPa (74.5% of 20 MPa PLA allowable) ✓

Mass estimate (PETG 1.27e-3 g/mm³):
  Arm cross-section: 62.4×45 − 59.4×42 = 2808 − 2494.8 = 313.2 mm²
  v7 arm cross-section: 62.4×53 − 59.2×49.8 = 3307 − 2948 = 359 mm²
  Savings: (359 − 313.2) × 111 ≈ 45.8 × 111 ≈ 5,089 mm³ → 6.5 g
  Target: ~57.68 − 6.5 = ~51.2 g vs 57.68 g baseline (−11 %)
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v14 (h=45mm, t_wall=1.5mm, pub_003_medium)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c            = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d       = c["bolt_diameter_clearance_mm"]
    lp           = c["load_point_mm"]
    min_wall     = c.get("min_wall_thickness_mm", 1.2)

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    bolt_r    = bolt_d / 2.0

    t_wall  = 1.5
    plate_t = min_wall
    margin  = bolt_r + plate_t

    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    # Wide arm: sides at bolt column y-positions (eliminates lateral plate bending)
    arm_y0  = float(min(by_coords))
    arm_y1  = float(max(by_coords))

    # h=45mm: |45 − lp[2]=39.6| = 5.4mm < 15mm load-node detection tolerance ✓
    h       = 45.0
    arm_len = lp[0] + 1.0

    outer_arm = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,     arm_y0,          0.0),
        gp_Pnt(arm_len, arm_y1,          h),
    ).Shape()

    inner_void = BRepPrimAPI_MakeBox(
        gp_Pnt(plate_t, arm_y0 + t_wall, t_wall),
        gp_Pnt(arm_len, arm_y1 - t_wall, h - t_wall),
    ).Shape()

    cut1 = BRepAlgoAPI_Cut(outer_arm, inner_void)
    cut1.Build()
    arm_shape = cut1.Shape()

    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,     plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    fuse1 = BRepAlgoAPI_Fuse(arm_shape, plate)
    fuse1.Build()
    shape = fuse1.Shape()

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
