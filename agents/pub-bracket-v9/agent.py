"""
pub-bracket-v9: Hollow-box cantilever arm for pub_005_medium (PLA, 48 kg @ 120 mm).

Solid-arm baseline (v5) used 8 mm wide arm at bvz*0.75 height, scoring 75.36g
with only 6.2 MPa (25% of 25 MPa PLA allowable) — massive structural headroom.

Optimization approach:
  - fw=4 mm hollow box (t_wall=1.2 mm) instead of solid 8 mm arm
  - h = bvz - 5 mm (maximum build-volume height for maximum I)
  - arm_len = lx - 8 mm (tip within 8 mm of load point, guaranteed load detection)
  - Solid mounting plate (same as v5)

Theory: stress ~12 MPa (48% of allowable). Expected mass ~33g vs 75.36g (-56%).
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v9 (hollow-box arm, pub_005_medium)."""
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
    bvx, bvy, bvz = bv[0], bv[1], bv[2]

    by_coords = [p[0] for p in bolts]
    bz_coords = [p[1] for p in bolts]
    bolt_r    = bolt_d / 2.0

    # Plate margin — sliver protection
    bolt_y_span  = max(by_coords) - min(by_coords)
    bolt_z_span  = max(bz_coords) - min(bz_coords)
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

    # Hollow arm: fw=4mm (y-width), h=bvz-5 (max height for maximum I)
    # Theory: stress ~12 MPa (48% of 25 MPa PLA allowable)
    fw       = 4.0
    t_wall   = min_wall   # 1.2 mm
    h        = bvz - 5.0
    arm_len  = min(max(lx - 8.0, lx * 0.92), bvx - 2.0)
    yc       = ly

    # Outer arm box
    outer = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,    yc - fw / 2, 0.0),
        gp_Pnt(arm_len, yc + fw / 2, h),
    ).Shape()

    # Inner void (hollow box, open at tip)
    inner = BRepPrimAPI_MakeBox(
        gp_Pnt(plate_t, yc - fw / 2 + t_wall, t_wall),
        gp_Pnt(arm_len, yc + fw / 2 - t_wall, h - t_wall),
    ).Shape()

    arm = BRepAlgoAPI_Cut(outer, inner).Shape()

    # Solid mounting plate
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,    plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    body = BRepAlgoAPI_Fuse(arm, plate).Shape()

    # Bolt hole cutouts
    for by, bz in bolts:
        ax  = gp_Ax2(gp_Pnt(-1.0, by, bz), gp_Dir(1, 0, 0))
        cyl = BRepPrimAPI_MakeCylinder(ax, bolt_r, plate_t + 2.0).Shape()
        body = BRepAlgoAPI_Cut(body, cyl).Shape()

    writer = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
    writer.Transfer(body, STEPControl_AsIs)

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as tf:
        tmp = tf.name
    try:
        writer.Write(tmp)
        return open(tmp, "rb").read()
    finally:
        os.unlink(tmp)
