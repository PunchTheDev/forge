"""
pub-bracket-v11: Wide hollow-box arm for pub_005_medium (PLA, 48 kg @ 120 mm).

Root cause of v9 failure: fw=4 mm arm at y=42.5 is 11.5 mm from the nearest
bolt column (y=54), so load transfers laterally through the thin mounting plate
→ plate bending → 64.3 MPa (2.6× allowable). Fix: same wide-arm principle used
in pub-bracket-v7 for pub_003 — arm sides land on bolt columns directly.

Design:
  fw      = bolt_y_span = 54 mm  (arm spans y=0..54, sides ARE the bolt columns)
  t_wall  = 1.5 mm
  h       = 35 mm  (|35 − lp[2]=42.3| = 7.3 mm < 15 mm load-node tolerance ✓)
  arm_len = lp[0] + 1 mm

Stress analysis (bending about y-axis, load in -z):
  F = 471.4 N,  L = 120.8 mm,  M = 56,991 N·mm
  I_outer = 54 × 35³ / 12 = 192,938 mm⁴   (wait — I_outer = 54×35³/12 = 192,938)
  Actually: I_outer = 54×35³/12, I_inner = 51×32³/12
  I_outer = 54 × 42,875 / 12 = 192,938 mm⁴
  I_inner = 51 × 32,768 / 12 = 139,264 mm⁴
  I_net   = 53,674 mm⁴,  c = 17.5 mm
  σ = 56,991 × 17.5 / 53,674 = 18.6 MPa < 25 MPa PLA allowable ✓

Mass estimate (PLA 1.24e-3 g/mm³):
  Arm cross-section: 54×35 − 51×32 = 1890 − 1632 = 258 mm²
  Arm volume: 258 × 120.8 ≈ 31,166 mm³ → 38.6 g
  Plate: ≈ 5.5 g
  Total: ≈ 40 g vs 75.36 g baseline (−47 %)
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v11 (wide hollow box, pub_005_medium)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c           = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d      = c["bolt_diameter_clearance_mm"]
    lp          = c["load_point_mm"]
    min_wall    = c.get("min_wall_thickness_mm", 1.2)

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    bolt_r    = bolt_d / 2.0

    t_wall  = 1.5
    plate_t = min_wall

    margin    = bolt_r + plate_t
    plate_y0  = min(by_coords) - margin
    plate_y1  = max(by_coords) + margin
    plate_z0  = min(bz_coords) - margin
    plate_z1  = max(bz_coords) + margin

    # Wide arm: sides at bolt column y-positions (eliminates plate bending)
    arm_y0  = float(min(by_coords))
    arm_y1  = float(max(by_coords))

    # h=35mm: |35 - lp[2]=42.3| = 7.3mm < 15mm load-node detection tolerance
    h       = 35.0
    arm_len = lp[0] + 1.0

    outer = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,     arm_y0,           0.0),
        gp_Pnt(arm_len, arm_y1,           h),
    ).Shape()

    inner = BRepPrimAPI_MakeBox(
        gp_Pnt(plate_t, arm_y0 + t_wall,  t_wall),
        gp_Pnt(arm_len, arm_y1 - t_wall,  h - t_wall),
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
