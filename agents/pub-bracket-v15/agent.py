"""
pub-bracket-v15: Reduced-height wide hollow arm for pub_003_medium (PETG).

Root cause of v14 failure (mesh-divergence, 190% deviation):
  h=45mm → inner ceiling at z=43.5mm, load z=39.6mm → only 3.9mm clearance.
  When the load node is <~8mm from the inner cavity ceiling, the thin 1.5mm
  wall over the hollow creates a mesh-dependent stress singularity.

Rule confirmed from v7 vs v14:
  v7  (h=53mm): inner ceiling at 51.4mm, 11.8mm clearance → STABLE, 11.33 MPa ✓
  v14 (h=45mm): inner ceiling at 43.5mm,  3.9mm clearance → UNSTABLE (190% dev)
  Minimum safe clearance: ~10mm from inner ceiling to load_z.

Fix: h=51mm → inner ceiling at 49.5mm, clearance = 9.9mm ≈ v7's regime.

Design:
  fw      = bolt_y_span = 62.4 mm  (sides at bolt columns y=0, y=62.4)
  t_wall  = 1.5 mm  (reduced from v7's 1.6mm)
  h       = 51 mm   |51 − lp[2]=39.6| = 11.4 mm < 15 mm load-node tolerance ✓
  arm_len = lp[0] + 1 mm = 111.2 mm
  plate   = solid, min_wall thick (same as v7)

Stress analysis (scaling from v7 FEA, 11.33 MPa at 20 MPa allowable):
  I_outer(h=51, t=1.5) = 62.4 × 51³ / 12 = 689,769 mm⁴
  I_inner(h=51, t=1.5) = 59.4 × 48³ / 12 = 547,430 mm⁴
  I_net   = 142,339 mm⁴,  c = 25.5 mm
  v7: I_net=165,794 mm⁴ (t=1.6, h=53),  c=26.5mm
  Stress ratio = (25.5/142,339) / (26.5/165,794) = 1.121
  FEA predicted = 11.33 × 1.121 ≈ 12.7 MPa (63.5% of 20 MPa allowable) ✓

Mass estimate (PETG 1.27e-3 g/mm³):
  Arm cross-section: 62.4×51 − 59.4×48 = 3182.4 − 2851.2 = 331.2 mm²
  v7 arm cross-section: 62.4×53 − 59.2×49.8 = 3307 − 2948 = 359 mm²
  Arm savings: (359 − 331.2) × 111.2 × 1.27e-3 ≈ 3.93 g
  Plate ≈ 9.8 g (same as v7)
  Target: ~57.68 − 3.93 ≈ 53.8 g vs 57.68 g (−6.8%)
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v15 (h=51mm, t_wall=1.5mm, pub_003_medium)."""
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

    # h=51mm: inner ceiling at z=49.5mm, 9.9mm above load_z=39.6mm
    # This matches the clearance regime of v7 (11.8mm) — mesh-stable.
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
