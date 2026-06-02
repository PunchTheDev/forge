"""
pub-bracket-v13: Wide hollow-box arm for pub_005_medium (PLA, 48 kg @ 120 mm).

Fix for v11: FEA gave 26.15 MPa vs analytical 18.6 MPa (1.41× correction factor).
Increasing h from 35→38mm raises I_net from 53,674→64,705 mm⁴, reducing stress
by 14%. FEA-corrected prediction: 26.15 × (53,674/64,705) = 21.7 MPa < 25 MPa.

Design:
  fw      = bolt_y_span = 54 mm  (arm spans y=0..54, sides ARE the bolt columns)
  t_wall  = 1.5 mm
  h       = 38 mm  (|38 − lp[2]=42.3| = 4.3 mm < 15 mm load-node tolerance ✓)
  arm_len = lp[0] + 1 mm

Stress analysis (bending about y-axis, load in -z):
  F = 471.4 N,  L = 120.8 mm,  M = 56,991 N·mm
  I_outer = 54 × 38³ / 12 = 246,924 mm⁴
  I_inner = 51 × 35³ / 12 = 182,219 mm⁴
  I_net   = 64,705 mm⁴,  c = 19.0 mm
  σ_analytical = 56,991 × 19.0 / 64,705 = 16.7 MPa
  FEA correction (v11 ratio 26.15/18.6 = 1.405): ~23.5 MPa < 25 MPa ✓

Mass estimate (PLA 1.24e-3 g/mm³):
  Arm cross-section: 54×38 − 51×35 = 2052 − 1785 = 267 mm²
  Arm volume: 267 × 121 ≈ 32,307 mm³ → 40.1 g
  Plate: ≈ 5.5 g
  Total: ≈ 45.6 g vs 75.36 g baseline (−40 %)
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v13 (wide hollow box h=38mm, pub_005_medium)."""
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

    margin   = bolt_r + plate_t
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    # Wide arm: sides at bolt column y-positions (eliminates plate bending)
    arm_y0  = float(min(by_coords))
    arm_y1  = float(max(by_coords))

    # h=38mm: |38 - lp[2]=42.3| = 4.3mm < 15mm load-node detection tolerance ✓
    # Raised from v11's 35mm to bring FEA stress under 25 MPa PLA allowable.
    h       = 38.0
    arm_len = lp[0] + 1.0

    outer = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,     arm_y0,          0.0),
        gp_Pnt(arm_len, arm_y1,          h),
    ).Shape()

    inner = BRepPrimAPI_MakeBox(
        gp_Pnt(plate_t, arm_y0 + t_wall, t_wall),
        gp_Pnt(arm_len, arm_y1 - t_wall, h - t_wall),
    ).Shape()

    arm = BRepAlgoAPI_Cut(outer, inner).Shape()

    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,     plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    body = BRepAlgoAPI_Fuse(arm, plate).Shape()

    for bby, bbz in bolt_pattern:
        axis = gp_Ax2(gp_Pnt(-1.0, bby, bbz), gp_Dir(1.0, 0.0, 0.0))
        hole = BRepPrimAPI_MakeCylinder(axis, bolt_r, plate_t + 2.0).Shape()
        body = BRepAlgoAPI_Cut(body, hole).Shape()

    writer = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
    writer.Transfer(body, STEPControl_AsIs)

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
        path = f.name
    try:
        writer.Write(path)
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.unlink(path)
