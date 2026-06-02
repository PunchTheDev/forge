"""
pub-bracket-v24: Minimum hollow arm + frame plate for pub_001_medium.

Improvement over v21b: reduces fw from 8mm to 3×mw=3.6mm (minimum hollow
cross-section) while keeping the proven frame plate and geometry from v21b.

Structural analysis (pub_001: F=464.48N, fw=3.6mm, mw=1.2mm, h=67mm):
  M = F × arm_len = 464.48 × 87.3 = 40,553 N·mm
  I = (3.6×67³ − 1.2×64.6³) / 12 = 63,270 mm⁴
  c = 33.5 mm
  σ_analytical = 40,553 × 33.5 / 63,270 = 21.5 MPa
  FEA/analytical ratio from v21b: 15.55/18.2 = 0.855
  σ_FEA_estimate = 0.855 × 21.5 = 18.4 MPa → 73.6% of 25 MPa ✓

Mesh clearance: inner ceiling = h − mw = 65.8mm, load_z = 38.6mm → 27.2mm >> 10mm ✓
Arm tip cap: inner ends at arm_len−mw so tip is inherently solid (learned from v22).
Frame plate: unchanged from v21b (2 interior voids for 3×2 bolt grid).

Estimated mass ≈ 20.7 g (−7.8% from v21b at 22.44 g).
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v24 (fw=3.6mm arm + frame plate, pub_001)."""
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

    # Plate margins — identical to v21b
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

    # Grid frame plate — same void-cut logic as v21b
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

    # Arm: fw = 3×mw = 3.6mm (minimum hollow cross-section)
    # Inner cavity ends at arm_len−mw (solid tip cap, from v22 learning)
    fw      = 3.0 * min_wall   # = 3.6mm
    t_wall  = min_wall
    h       = 67.0             # proven in v21b (62mm gave mesh divergence)
    arm_len = max(lx - 12.0, 1.0)
    arm_len = min(arm_len, bv[0] - 2.0)
    yc      = ly

    outer = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,     yc - fw / 2,            0.0),
        gp_Pnt(arm_len, yc + fw / 2,            h),
    ).Shape()
    # Inner ends at arm_len-t_wall: solid tip cap avoids open-edge stress concentration
    inner = BRepPrimAPI_MakeBox(
        gp_Pnt(plate_t,          yc - fw / 2 + t_wall, t_wall),
        gp_Pnt(arm_len - t_wall, yc + fw / 2 - t_wall, h - t_wall),
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
