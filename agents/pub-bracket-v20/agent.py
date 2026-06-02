"""
pub-bracket-v20: Grid frame plate for pub_001_medium (PLA, 47 kg @ 99 mm).

v19 achieved 27.956g at 15.1 MPa (60.4% of 25 MPa allowable). The mounting
plate is a solid 1.2mm sheet. pub_001 has a 3-column × 2-row bolt pattern
(y=0, 42.8, 85.6 and z=0, 42.8) — a grid frame plate removes the two interior
voids between the column/row strips, cutting ~3.3g from the plate.

pub_001_medium parameters:
  load_point:   [99.3, 46.9, 38.6]
  bolt_pattern: 6 bolts at y∈{0,42.8,85.6}, z∈{0,42.8}
  bolt_d:       7.0mm → bolt_r = 3.5mm
  min_wall:     1.2mm
  build_vol:    [134.1, 93.7, 77.3]
  material:     PLA, yield=25 MPa

Grid frame strip layout (strip_w = bolt_r + min_wall = 4.7mm):
  Column strips centered on y=0, 42.8, 85.6 — each ±4.7mm
  Row strips centered on z=0, 42.8 — each ±4.7mm
  Interior gaps between columns: y=[4.7..38.1] and y=[47.5..80.9]
  Interior gap between rows:     z=[4.7..38.1]

  2 rectangular voids cut from plate:
    Void 1: y=[4.7..38.1], z=[4.7..38.1]  → 33.4 × 33.4 = 1116 mm²
    Void 2: y=[47.5..80.9], z=[4.7..38.1]  → 33.4 × 33.4 = 1116 mm²

Mass analysis (PLA 1.24e-3 g/mm³, plate_t = 1.2mm):
  Solid plate ≈ 4959 mm²
  Total void area = 2 × 1116 = 2231 mm²
  Mass removed = 2231 × 1.2 × 1.24e-3 ≈ 3.32g
  Target: 27.956 - 3.32 ≈ 24.6g

Arm: identical to v19 (fw=8mm, h=72.3mm, t_wall=1.2mm).
  Arm at y=42.9..50.9mm overlaps middle column strip y=38.1..47.5mm → 4.6mm ✓
  Arm height 72.3mm spans both bolt rows (z=0 and z=42.8mm, strip ends z=47.5mm) ✓
  Both row strips and all three column strips intact — all 6 bolt holes connected ✓

Stress: arm geometry unchanged → predicted ~15.1 MPa (60.4% of 25 MPa) ✓
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v20 (grid frame plate, pub_001_medium)."""
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

    by_cols = sorted(set(p[0] for p in bolts))  # unique y column positions
    bz_rows = sorted(set(p[1] for p in bolts))  # unique z row positions
    bolt_r  = bolt_d / 2.0
    strip_w = bolt_r + min_wall  # 4.7mm for pub_001

    # Sliver-safe plate margins (identical to v19)
    bolt_y_span  = max(by_cols) - min(by_cols)
    bolt_z_span  = max(bz_rows) - min(bz_rows)
    bvy          = bv[1]
    y_half_avail = (bvy - bolt_y_span) / 2.0 - 0.5
    z_half_avail = (bvz - bolt_z_span) / 2.0 - 0.5
    margin_y     = min(strip_w, max(0.0, y_half_avail))
    margin_z     = min(strip_w, max(0.0, z_half_avail))
    MIN_SLIVER   = 0.5
    if 0.0 < margin_y - bolt_r < MIN_SLIVER:
        margin_y = bolt_r - MIN_SLIVER
    if 0.0 < margin_z - bolt_r < MIN_SLIVER:
        margin_z = bolt_r - MIN_SLIVER

    plate_t  = min_wall
    plate_y0 = min(by_cols) - margin_y
    plate_y1 = max(by_cols) + margin_y
    plate_z0 = min(bz_rows) - margin_z
    plate_z1 = max(bz_rows) + margin_z

    # Build grid frame plate: cut interior voids between each col/row strip pair
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,     plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    # Column gap edges: right edge of left strip → left edge of right strip
    col_gap_starts = [y + strip_w for y in by_cols[:-1]]
    col_gap_ends   = [y - strip_w for y in by_cols[1:]]
    row_gap_starts = [z + strip_w for z in bz_rows[:-1]]
    row_gap_ends   = [z - strip_w for z in bz_rows[1:]]

    for y0, y1 in zip(col_gap_starts, col_gap_ends):
        for z0, z1 in zip(row_gap_starts, row_gap_ends):
            if y0 < y1 and z0 < z1:
                void = BRepPrimAPI_MakeBox(
                    gp_Pnt(0.0,     y0, z0),
                    gp_Pnt(plate_t, y1, z1),
                ).Shape()
                cut  = BRepAlgoAPI_Cut(plate, void)
                cut.Build()
                plate = cut.Shape()

    # Arm: identical to v19 — fw=8mm hollow, t_wall=min_wall, h=bvz-5
    fw      = 8.0
    t_wall  = min_wall
    h       = bvz - 5.0
    arm_len = min(max(lx - 8.0, lx * 0.92), bv[0] - 2.0)
    yc      = ly

    outer = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,     yc - fw / 2,          0.0),
        gp_Pnt(arm_len, yc + fw / 2,          h),
    ).Shape()
    inner = BRepPrimAPI_MakeBox(
        gp_Pnt(plate_t, yc - fw / 2 + t_wall, t_wall),
        gp_Pnt(arm_len, yc + fw / 2 - t_wall, h - t_wall),
    ).Shape()
    arm = BRepAlgoAPI_Cut(outer, inner).Shape()

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
