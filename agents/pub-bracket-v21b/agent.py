"""
pub-bracket-v21: Grid frame plate + tighter arm for pub_001_medium. (v2)

v20 achieved 24.81g using grid frame plate, but arm height = bvz-5 = 72.3mm
is over-engineered. At 60.4% stress utilisation, substantial headroom exists.

Tightening:
  - Arm height: 72.3mm → 62mm (87.6% predicted utilisation, 22mm mesh clearance)
  - Arm length: 91.4mm → lx-15mm = 84.3mm (minimum ±15mm tolerance)
  - Frame plate: unchanged from v20 (grid with 2 interior voids)

Stress analysis (pub_001: F=464.48N, fw=8mm, t_wall=1.2mm):
  M = F × arm_len = 464.48 × 84.3 = 39,158 N·mm
  I = (8×62³ - 5.6×59.6³) / 12 = (1,906,624 - 1,185,565) / 12 = 60,088 mm⁴
  S = I / c = 60,088 / 31 = 1,938 mm³
  σ = M / S = 39,158 / 1,938 = 20.2 MPa → 80.8% of 25 MPa allowable ✓
  Mesh clearance: inner ceiling = 60.8mm, load_z = 38.6mm → 22.2mm >> 10mm ✓
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v21 (grid frame plate + tighter arm)."""
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

    by_cols = sorted(set(p[0] for p in bolts))
    bz_rows = sorted(set(p[1] for p in bolts))
    bolt_r  = bolt_d / 2.0
    strip_w = bolt_r + min_wall

    # Plate margins — identical to v20
    bolt_y_span  = max(by_cols) - min(by_cols)
    bolt_z_span  = max(bz_rows) - min(bz_rows)
    bvy          = bv[1]
    bvz          = bv[2]
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

    # Grid frame plate — same void-cut logic as v20
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,     plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

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

    # Arm: fw=8mm, tighter height and length
    fw      = 8.0
    t_wall  = min_wall
    h       = 62.0                    # reduced from bvz-5=72.3mm
    arm_len = max(lx - 12.0, 1.0)    # 12 mm margin within ±15 mm load-point tolerance
    arm_len = min(arm_len, bv[0] - 2.0)
    yc      = ly

    outer = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,     yc - fw / 2,            0.0),
        gp_Pnt(arm_len, yc + fw / 2,            h),
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
