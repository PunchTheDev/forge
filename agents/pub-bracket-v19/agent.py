"""
pub-bracket-v19: Thinner-wall hollow arm for pub_001_medium (PLA, 47 kg @ 99 mm).

v10 achieved 32.98g at 12.34 MPa (49.4% of 25 MPa allowable) with t_wall=1.5mm.
50.6% stress margin remaining — substantial room to thin walls to min_wall (1.2mm).

Mesh stability check (≥10mm clearance rule):
  h = bvz − 5 = 72.3mm, t_wall=1.2mm → inner ceiling = 72.3 − 1.2 = 71.1mm
  load_z = 38.6mm → clearance = 71.1 − 38.6 = 32.5mm — very safe ✓
  (arm is tall relative to load point; no mesh risk)

Stress analysis (scaling from v10 FEA, 12.34 MPa at 25 MPa allowable):
  I_outer = 8 × 72.3³ / 12 = 252,203 mm⁴  (unchanged)
  I_inner(t=1.2): (8−2.4) × (72.3−2.4)³ / 12 = 5.6 × 69.9³ / 12
    69.9³ = 341,732  →  5.6 × 341,732 / 12 = 159,474 mm⁴
  I_net   = 252,203 − 159,474 = 92,729 mm⁴  (vs 113,405 mm⁴ in v10)
  Stress ratio = 113,405 / 92,729 = 1.223
  FEA predicted = 12.34 × 1.223 ≈ 15.1 MPa (60.4% of 25 MPa PLA) ✓

Mass estimate (PLA 1.24e-3 g/mm³):
  Arm cross-section v10: 8×72.3 − 5×69.3 = 578.4 − 346.5 = 231.9 mm²
  Arm cross-section v19: 8×72.3 − 5.6×69.9 = 578.4 − 391.4 = 187.0 mm²
  Arm savings: (231.9 − 187.0) × 91.3 × 1.24e-3 ≈ 5.08 g
  Total: 32.98 − 5.08 ≈ 27.9 g
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v19 (t_wall=min_wall hollow arm, pub_001_medium)."""
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

    # Mounting plate margins (sliver-safe, same as v10)
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

    # Arm: fw=8mm hollow, t_wall=min_wall (1.2mm)
    fw      = 8.0
    t_wall  = min_wall  # 1.2mm — minimum allowed
    h       = bvz - 5.0
    arm_len = min(max(lx - 8.0, lx * 0.92), bv[0] - 2.0)
    yc      = ly

    outer = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,     yc - fw / 2,          0.0),
        gp_Pnt(arm_len, yc + fw / 2,          h),
    ).Shape()

    # Inner void: open at tip, starts at plate_t in x, t_wall inset on y and z
    inner = BRepPrimAPI_MakeBox(
        gp_Pnt(plate_t, yc - fw / 2 + t_wall, t_wall),
        gp_Pnt(arm_len, yc + fw / 2 - t_wall, h - t_wall),
    ).Shape()

    arm = BRepAlgoAPI_Cut(outer, inner).Shape()

    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,     plate_y0, plate_z0),
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
