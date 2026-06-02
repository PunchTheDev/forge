"""
pub-bracket-v18: Thinner-wall wide hollow arm for pub_005_medium (PLA, 48 kg @ 120 mm).

v16 achieved 52.37g at 13.06 MPa (52.2% of 25 MPa allowable) with t_wall=1.5mm.
47.8% stress margin remaining — significant room to thin walls to min_wall (1.2mm).

Mesh stability check (≥10mm clearance rule):
  h=54mm, t_wall=1.2mm → inner ceiling = 54 − 1.2 = 52.8mm
  load_z = 42.3mm → clearance = 52.8 − 42.3 = 10.5mm ≥ 10mm ✓

Stress analysis (scaling from v16, 13.06 MPa):
  I_outer = 54 × 54³ / 12 = 708,588 mm⁴  (same as v16)
  I_inner(t=1.2): (54−2.4) × (54−2.4)³ / 12 = 51.6 × 51.6³ / 12
    51.6³ = 137,389  →  51.6 × 137,389 / 12 = 590,893 mm⁴
  I_net   = 708,588 − 590,893 = 117,695 mm⁴  (vs 143,697 mm⁴ in v16)
  Stress ratio = 143,697 / 117,695 = 1.221
  FEA predicted = 13.06 × 1.221 ≈ 15.9 MPa (63.7% of 25 MPa PLA) ✓

Mass estimate (PLA 1.24e-3 g/mm³):
  Arm cross-section v16: 54×54 − 51×51 = 2916 − 2601 = 315 mm²
  Arm cross-section v18: 54×54 − 51.6×51.6 = 2916 − 2662.6 = 253.4 mm²
  Arm savings: (315 − 253.4) × 120.8 × 1.24e-3 ≈ 9.23 g
  Total: 52.37 − 9.23 ≈ 43.1 g
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v18 (h=54mm, t_wall=min_wall, pub_005_medium)."""
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

    t_wall  = min_wall  # 1.2mm — minimum allowed wall thickness
    plate_t = min_wall
    margin  = bolt_r + plate_t

    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    # Wide arm: sides at bolt columns y=0 and y=54mm (eliminates plate bending)
    arm_y0  = float(min(by_coords))
    arm_y1  = float(max(by_coords))

    # h=54mm: inner ceiling at 52.8mm (t_wall=1.2), 10.5mm above load_z=42.3mm ✓
    h       = 54.0
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
