"""
pub-bracket-v17: Thinner-wall wide hollow arm for pub_003_medium (PETG).

v15 achieved 53.80g at 13.05 MPa (65.3% of 20 MPa allowable) with t_wall=1.5mm.
Still 34.7% stress margin — room to thin the walls to min_wall (1.2mm).

Mesh stability check (≥10mm clearance rule):
  h=51mm, t_wall=1.2mm → inner ceiling = 51 − 1.2 = 49.8mm
  load_z = 39.6mm → clearance = 49.8 − 39.6 = 10.2mm ≥ 10mm ✓

Stress analysis (scaling from v15, 13.05 MPa at 20 MPa allowable):
  I_outer = 62.4 × 51³ / 12 = 689,769 mm⁴  (same as v15)
  I_inner(t=1.2): (62.4−2.4) × (51−2.4)³ / 12 = 60.0 × 48.6³ / 12
    48.6³ = 114,791  →  60.0 × 114,791 / 12 = 573,954 mm⁴
  I_net   = 689,769 − 573,954 = 115,815 mm⁴  (vs 142,339 mm⁴ in v15)
  Stress ratio = 142,339 / 115,815 = 1.229
  FEA predicted = 13.05 × 1.229 ≈ 16.0 MPa (80.2% of 20 MPa) ✓

Mass estimate (PETG 1.27e-3 g/mm³):
  Arm cross-section v15: 62.4×51 − 59.4×48 = 3182.4 − 2851.2 = 331.2 mm²
  Arm cross-section v17: 62.4×51 − 60.0×48.6 = 3182.4 − 2916.0 = 266.4 mm²
  Arm savings: (331.2 − 266.4) × 111.2 × 1.27e-3 ≈ 9.14 g
  Total: 53.80 − 9.14 ≈ 44.7 g
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v17 (h=51mm, t_wall=min_wall, pub_003_medium)."""
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

    # Wide arm: sides at bolt column y-positions (eliminates lateral plate bending)
    arm_y0  = float(min(by_coords))
    arm_y1  = float(max(by_coords))

    # h=51mm: inner ceiling at z=49.8mm (with t_wall=1.2), 10.2mm above load_z=39.6mm ✓
    h       = 51.0
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
