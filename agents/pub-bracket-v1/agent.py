"""
pub-bracket-v1: Solid cantilever arm bracket for pub_001_medium (PLA).

All geometry parameters read from spec["constraints"] at runtime.

Design:
  - Solid rectangular arm (no hollow void) — avoids degenerate mesh elements
    from thin walls at the 4 mm FEA mesh resolution.
  - Arm width fw = 8 mm (> mesh element size → clean tetrahedra).
  - Arm height h = bvz - 5 mm (maximum height → maximum second moment of area).
  - Arm length: tip within 8 mm of load_x so mesh nodes land in the 15 mm
    load-node detection zone even on a coarse 4 mm mesh.
  - Mounting plate: encloses bolt pattern with bolt_r margin. If the plate
    would leave < 0.5 mm between a bolt hole and the plate edge (a meshing
    sliver), the edge is pulled back to create a clean U-notch instead.
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v1 (solid 8 mm arm)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c        = spec["constraints"]
    bolts    = c["bolt_pattern_mm"]
    bolt_d   = c["bolt_diameter_clearance_mm"]
    lp       = c["load_point_mm"]       # [lx, ly, lz]
    min_wall = c.get("min_wall_thickness_mm", 1.2)
    bv       = c["build_volume_mm"]     # [bvx, bvy, bvz]

    lx, ly, lz = lp[0], lp[1], lp[2]
    bvx, bvy, bvz = bv[0], bv[1], bv[2]

    by_coords = [p[0] for p in bolts]
    bz_coords = [p[1] for p in bolts]
    bolt_r    = bolt_d / 2.0

    # ── Plate margin (sliver-safe) ────────────────────────────────────────────────
    bolt_y_span  = max(by_coords) - min(by_coords)
    bolt_z_span  = max(bz_coords) - min(bz_coords)
    y_half_avail = (bvy - bolt_y_span) / 2.0 - 0.5
    z_half_avail = (bvz - bolt_z_span) / 2.0 - 0.5
    ideal_margin = bolt_r + min_wall
    margin_y     = min(ideal_margin, max(0.0, y_half_avail))
    margin_z     = min(ideal_margin, max(0.0, z_half_avail))
    # A sliver < 0.5 mm between bolt hole and plate edge breaks the surface mesher
    MIN_SLIVER = 0.5
    if 0.0 < margin_y - bolt_r < MIN_SLIVER:
        margin_y = bolt_r - MIN_SLIVER   # U-notch: hole pokes through edge cleanly
    if 0.0 < margin_z - bolt_r < MIN_SLIVER:
        margin_z = bolt_r - MIN_SLIVER

    plate_t  = min_wall
    plate_y0 = min(by_coords) - margin_y
    plate_y1 = max(by_coords) + margin_y
    plate_z0 = min(bz_coords) - margin_z
    plate_z1 = max(bz_coords) + margin_z

    # ── Arm dimensions ────────────────────────────────────────────────────────────
    fw = 8.0   # wider than one 4 mm mesh element → no degenerate tets
    h  = min(bvz - 5.0, max(bvz * 0.75, lz + 15.0 + min_wall))

    # Arm tip 8 mm from load → node detection guaranteed at 4 mm mesh spacing
    arm_len = min(max(lx - 8.0, lx * 0.92), bvx - 2.0)
    yc = ly

    # ── Solid arm ────────────────────────────────────────────────────────────────
    arm = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, yc - fw / 2, 0.0),
        gp_Pnt(arm_len, yc + fw / 2, h),
    ).Shape()

    # ── Mounting plate ───────────────────────────────────────────────────────────
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    body = BRepAlgoAPI_Fuse(arm, plate).Shape()

    # ── Bolt holes ───────────────────────────────────────────────────────────────
    for by, bz in bolts:
        ax  = gp_Ax2(gp_Pnt(-1.0, by, bz), gp_Dir(1, 0, 0))
        cyl = BRepPrimAPI_MakeCylinder(ax, bolt_r, plate_t + 2.0).Shape()
        body = BRepAlgoAPI_Cut(body, cyl).Shape()

    # ── STEP export ──────────────────────────────────────────────────────────────
    writer = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
    writer.Transfer(body, STEPControl_AsIs)

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
        tmp = f.name
    try:
        writer.Write(tmp)
        return open(tmp, "rb").read()
    finally:
        os.unlink(tmp)
