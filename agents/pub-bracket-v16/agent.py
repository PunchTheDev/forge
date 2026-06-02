"""
pub-bracket-v16: Wide hollow arm for pub_005_medium (PLA, 48 kg @ 120 mm).

Root cause of v13 failure (mesh-divergence, 213% deviation):
  h=38mm → arm top BELOW load_z=42.3mm (load above arm).
  Load applied to outer top face: thin 1.5mm wall over hollow → singularity.

Root cause of v11 failure (stress): h=35mm → 26.15 MPa > 25 MPa PLA allowable.
  FEA correction factor for pub_005: 1.41× over analytical beam theory.

Rule: inner ceiling must be ≥10mm above load_z to avoid mesh-dependent failure.
  Required: h − t_wall > load_z + 10mm → h > 42.3 + 10 + 1.5 = 53.8mm → h=54mm.
  h=54mm: inner ceiling at z=52.5mm, clearance = 52.5 − 42.3 = 10.2mm ✓
  (matches pub_003 v7 regime: 11.8mm clearance → stable at 11.33 MPa)

Design:
  fw      = bolt_y_span = 54 mm  (arm spans y=0..54mm, sides at bolt columns)
  t_wall  = 1.5 mm
  h       = 54 mm   inner ceiling at 52.5mm, 10.2mm above load_z=42.3mm ✓
  arm_len = lp[0] + 1 mm = 120.8 mm

Stress analysis (bending about y-axis, load in −z):
  F = 471.4 N,  L = 119.8 mm,  M = 56,482 N·mm
  I_outer = 54 × 54³ / 12 = 708,588 mm⁴
  I_inner = 51 × 51³ / 12 = 564,891 mm⁴
  I_net   = 143,697 mm⁴,  c = 27.0 mm
  σ_analytical = 56,482 × 27.0 / 143,697 = 10.6 MPa
  FEA correction (pub_005 factor 1.41×): ~14.9 MPa < 25 MPa ✓ (60% util)

Mass estimate (PLA 1.24e-3 g/mm³):
  Arm cross-section: 54×54 − 51×51 = 2916 − 2601 = 315 mm²
  Arm volume: 315 × 120.8 ≈ 38,052 mm³ → 47.2 g
  Plate: ~5.9 g
  Total: ~53.1 g vs 75.36 g baseline (−30%)
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v16 (h=54mm wide hollow arm, pub_005_medium)."""
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

    # Wide arm: sides at bolt columns y=0 and y=54mm (eliminates plate bending)
    arm_y0  = float(min(by_coords))
    arm_y1  = float(max(by_coords))

    # h=54mm: inner ceiling at z=52.5mm, 10.2mm clearance above load_z=42.3mm
    # Same stability regime as pub_003 v7 (11.8mm clearance, mesh-stable).
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
