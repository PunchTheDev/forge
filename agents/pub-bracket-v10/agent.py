"""
pub-bracket-v10: Hollow 8 mm arm for pub_001_medium (PLA, 47 kg @ 99 mm).

Root cause of v8 failure: fw=4 mm produced an 18:1 z/y aspect-ratio hollow tube
that failed FEA mesh convergence. Fix: keep fw=8 mm (same as solid v1), just
hollow it out. At fw=8 mm the arm left edge (y=42.9) lands essentially on the
middle bolt column (y=42.8), giving a direct load path with no plate bending.

Design:
  fw      = 8 mm   (arm y-width — matches v1 solid, left edge ≈ bolt col y=42.8)
  t_wall  = 1.5 mm (slight over-min for mesh stability)
  h       = bvz - 5 mm (maximum build-volume height for maximum I)
  arm_len = lx - 8 mm

Stress analysis (bending about y-axis, load in -z):
  F = 464.48 N,  L ≈ 91.3 mm,  M = 42,387 N·mm
  I_outer = 8 × 72.3³ / 12 = 252,203 mm⁴
  I_inner = 5 × 69.3³ / 12 = 138,798 mm⁴
  I_net   = 113,405 mm⁴,  c = 36.15 mm
  σ = 42,387 × 36.15 / 113,405 = 13.5 MPa < 25 MPa PLA allowable ✓

Mass estimate (PLA 1.24e-3 g/mm³):
  Arm cross-section: 8×72.3 − 5×69.3 = 578 − 347 = 231 mm²
  Arm volume: 231 × 91.3 ≈ 21,090 mm³ → 26.1 g
  Plate: ≈ 5.5 g
  Total: ≈ 32 g vs 58.72 g baseline (−45 %)
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v10 (hollow 8 mm arm, pub_001_medium)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c        = spec["constraints"]
    bolts    = c["bolt_pattern_mm"]
    bolt_d   = c["bolt_diameter_clearance_mm"]
    lp       = c["load_point_mm"]
    min_wall = c.get("min_wall_thickness_mm", 1.2)
    bv       = c["build_volume_mm"]

    lx, ly, lz = lp[0], lp[1], lp[2]
    bvz        = bv[2]

    by_coords = [p[0] for p in bolts]
    bz_coords = [p[1] for p in bolts]
    bolt_r    = bolt_d / 2.0

    # Mounting plate margins (sliver-safe, same as v1)
    bolt_y_span  = max(by_coords) - min(by_coords)
    bolt_z_span  = max(bz_coords) - min(bz_coords)
    bvy, _       = bv[1], bv[0]
    y_half_avail = (bvy - bolt_y_span) / 2.0 - 0.5
    z_half_avail = (bvz - bolt_z_span) / 2.0 - 0.5
    ideal_margin = bolt_r + min_wall
    margin_y     = min(ideal_margin, max(0.0, y_half_avail))
    margin_z     = min(ideal_margin, max(0.0, z_half_avail))
    MIN_SLIVER   = 0.5
    if 0.0 < margin_y - bolt_r < MIN_SLIVER:
        margin_y = bolt_r - MIN_SLIVER
    if 0.0 < margin_z - bolt_r < MIN_SLIVER:
        margin_z = bolt_r - MIN_SLIVER

    plate_t  = min_wall
    plate_y0 = min(by_coords) - margin_y
    plate_y1 = max(by_coords) + margin_y
    plate_z0 = min(bz_coords) - margin_z
    plate_z1 = max(bz_coords) + margin_z

    # Arm: fw=8 mm hollow (t_wall=1.5 mm)
    fw      = 8.0
    t_wall  = 1.5
    h       = bvz - 5.0
    arm_len = min(max(lx - 8.0, lx * 0.92), bv[0] - 2.0)
    yc      = ly

    outer = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,     yc - fw / 2,          0.0),
        gp_Pnt(arm_len, yc + fw / 2,          h),
    ).Shape()

    # Inner void: open at tip (no sliver), starts at plate_t in x, t_wall inset on y and z
    inner = BRepPrimAPI_MakeBox(
        gp_Pnt(plate_t, yc - fw / 2 + t_wall, t_wall),
        gp_Pnt(arm_len, yc + fw / 2 - t_wall, h - t_wall),
    ).Shape()

    arm = BRepAlgoAPI_Cut(outer, inner).Shape()

    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,    plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    body = BRepAlgoAPI_Fuse(arm, plate).Shape()

    for by, bz in bolts:
        ax   = gp_Ax2(gp_Pnt(-1.0, by, bz), gp_Dir(1, 0, 0))
        hole = BRepPrimAPI_MakeCylinder(ax, bolt_r, plate_t + 2.0).Shape()
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
