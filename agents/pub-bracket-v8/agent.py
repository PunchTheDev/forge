"""
pub-bracket-v8: Reduced-height wide hollow arm + frame plate for pub_003_medium (PETG).

Builds on v7 (57.68g, 11.3 MPa, 56.5% utilization). Two changes:
  1. Reduce h: 53 → 40mm — 56.5% utilization means the arm carries only
     56% of allowable load, so section modulus can be reduced.
  2. Frame plate: remove solid plate interior, keep only perimeter strips
     around bolt rows/columns (same insight as spec-003 v15, saved ~17g there).

pub_003_medium parameters:
  load_point:   [110.2, 43.6, 39.6]
  bolt_pattern: [(0,0),(62.4,0),(0,62.4),(62.4,62.4)] — 62.4mm span
  bolt_d:       6.5mm → bolt_r = 3.25mm
  min_wall:     1.2mm
  build_vol:    [158.9, 87.2, 79.3]
  material:     PETG, yield=40 MPa, allowable=20 MPa (SF=2.0)
  load:         517.31 N

Bending stress (approximate, beam theory):
  M = 517.31 × 2.0 × 110.2 = 114,015 N·mm
  h=40, fw=62.4, t_wall=1.6mm:
  I_outer = 62.4 × 40³/12 = 332,800 mm⁴
  I_inner = 59.2 × 36.8³/12 = 219,278 mm⁴
  I_net   = 113,522 mm⁴,  c = 20mm
  σ_analytic = 114,015 × 20 / 113,522 = 20.1 MPa

  v7 FEA was 1.61× lower than analytic estimate (18.2 analytic vs 11.3 FEA).
  Adjusted estimate: 20.1 / 1.61 = 12.5 MPa (62.5% of 20 MPa) — safe margin.
  h=40 is within ±15mm of lp[2]=39.6: |40-39.6|=0.4mm ✓

Frame plate mass (PETG 1.27e-3 g/mm³):
  bolt_r + min_wall = 3.25 + 1.2 = 4.45mm strip around each bolt row/col
  Plate exterior: 71.3mm × 71.3mm → solid = 5,084 mm²
  Frame strips (only perimeter): ~2,210 mm² → saves ~4.4g vs solid plate

Mass estimate (h=40mm, frame plate):
  Net arm: ~37,810 mm³ × 1.27e-3 ≈ 48.0g  (was 44,605 mm³ → 56.6g at h=53)
  Frame plate net: ~3.1g  (was ~8.7g solid)
  Total estimate: ~51g  (saves ~7g vs v7's 57.68g)
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v8 (reduced h, frame plate, PETG pub_003)."""
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
    strip_w = bolt_r + min_wall   # 4.45mm strip around each bolt row/col

    plate_t = min_wall
    plate_y0 = min(by_coords) - strip_w
    plate_y1 = max(by_coords) + strip_w
    plate_z0 = min(bz_coords) - strip_w
    plate_z1 = max(bz_coords) + strip_w

    arm_y0 = float(min(by_coords))
    arm_y1 = float(max(by_coords))
    h = 40.0          # |40 - 39.6| = 0.4mm < 15mm load tolerance ✓
    t_wall = 1.6      # PETG needs thicker walls for stress
    arm_len = lp[0] + 1.0

    # Wide hollow box arm: sides at bolt column lines (y=0, y=62.4mm)
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

    # Frame plate: solid plate minus interior cutout
    # Keep only perimeter strips of width strip_w around bolt rows/columns
    full_plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    # Interior cutout: region between the bolt column/row strips
    cutout_y0 = plate_y0 + strip_w   # = min(by_coords) = 0.0
    cutout_y1 = plate_y1 - strip_w   # = max(by_coords) = 62.4
    cutout_z0 = plate_z0 + strip_w   # = min(bz_coords) = 0.0
    cutout_z1 = plate_z1 - strip_w   # = max(bz_coords) = 62.4

    plate_cutout = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, cutout_y0, cutout_z0),
        gp_Pnt(plate_t, cutout_y1, cutout_z1),
    ).Shape()

    cut2 = BRepAlgoAPI_Cut(full_plate, plate_cutout)
    cut2.Build()
    plate_shape = cut2.Shape()

    fuse1 = BRepAlgoAPI_Fuse(arm_shape, plate_shape)
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
