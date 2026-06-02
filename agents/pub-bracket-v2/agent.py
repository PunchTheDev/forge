"""
pub-bracket-v2: Parametric hollow-box cantilever bracket for pub_002_medium.

Target: Aluminum 6061-T6, 32 kg load at ~126 mm arm.
Design: hollow I-section arm + compact mounting plate.
  - Arm depth (z-height): 80% of build volume z, centered on load_z
  - Arm width (y): 2 × min_wall on each flange + min_wall web
  - Arm length: approaches load_x within 15 mm tolerance
  - Mounting plate: covers bolt pattern + margin, clipped to build volume
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v2 (adaptive hollow box arm, Al6061)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d = c["bolt_diameter_clearance_mm"]
    lp = c["load_point_mm"]          # [lx, ly, lz]
    wall = c.get("min_wall_thickness_mm", 1.2)
    bv = c["build_volume_mm"]        # [bvx, bvy, bvz]

    lx, ly, lz = lp[0], lp[1], lp[2]
    bvx, bvy, bvz = bv[0], bv[1], bv[2]

    bolt_r = bolt_d / 2.0
    clearance = bolt_r + wall

    # Mounting plate: rectangle over bolt holes + clearance margin
    plate_thick = wall
    raw_y0 = min(p[0] for p in bolt_pattern) - clearance
    raw_y1 = max(p[0] for p in bolt_pattern) + clearance
    raw_z0 = min(p[1] for p in bolt_pattern) - clearance
    raw_z1 = max(p[1] for p in bolt_pattern) + clearance

    # Clip plate to build volume symmetrically
    yspan = raw_y1 - raw_y0
    if yspan > bvy - 0.5:
        cut = (yspan - (bvy - 0.5)) / 2.0
        plate_y0, plate_y1 = raw_y0 + cut, raw_y1 - cut
    else:
        plate_y0, plate_y1 = raw_y0, raw_y1

    zspan = raw_z1 - raw_z0
    if zspan > bvz - 0.5:
        cut = (zspan - (bvz - 0.5)) / 2.0
        plate_z0, plate_z1 = raw_z0 + cut, raw_z1 - cut
    else:
        plate_z0, plate_z1 = raw_z0, raw_z1

    # Arm geometry: hollow rectangular section extending in x
    # Width: 3 × wall (two outer walls + hollow interior)
    arm_w = 3.0 * wall

    # Height: 80% of build volume z, must clear the load zone top
    h_max  = bvz - 5.0
    h_want = bvz * 0.80
    h_min  = lz + 15.0 + wall        # arm top well above load zone
    h      = min(h_max, max(h_want, h_min))

    # Length: within 15 mm of load point, capped at build volume
    reach = max(lx - 15.0, lx * 0.85)
    arm_len = min(reach, bvx - 2.0)

    y_mid = ly    # center arm on load y

    # Hollow box arm (outer minus inner void)
    outer = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,    y_mid - arm_w / 2, 0.0),
        gp_Pnt(arm_len, y_mid + arm_w / 2, h),
    ).Shape()

    void = BRepPrimAPI_MakeBox(
        gp_Pnt(plate_thick, y_mid - arm_w / 2 + wall, wall),
        gp_Pnt(arm_len,     y_mid + arm_w / 2 - wall, h - wall),
    ).Shape()

    arm = BRepAlgoAPI_Cut(outer, void).Shape()

    # Mounting plate
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,        plate_y0, plate_z0),
        gp_Pnt(plate_thick, plate_y1, plate_z1),
    ).Shape()

    body = BRepAlgoAPI_Fuse(arm, plate).Shape()

    # Bolt holes through the plate
    for by, bz in bolt_pattern:
        axis = gp_Ax2(gp_Pnt(-1.0, by, bz), gp_Dir(1, 0, 0))
        cyl  = BRepPrimAPI_MakeCylinder(axis, bolt_r, plate_thick + 2.0).Shape()
        body = BRepAlgoAPI_Cut(body, cyl).Shape()

    # STEP export
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
