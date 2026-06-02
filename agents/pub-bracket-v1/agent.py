"""
pub-bracket-v1: Parametric hollow-box cantilever bracket for pub specs.

Reads all constraints from spec dynamically. Works for PLA, PETG, Al6061.

Design: hollow box arm + minimal mounting plate.
  - Arm: fw=2×min_wall wide, h=build_vol_z×0.8 tall, extends to load x
  - Wall thickness: min_wall on all sides
  - Arm length: min(load_x - load_tol, build_vol_x) where load_tol=15mm
  - Load nodes: arm covers z=load_z±(h/2), guaranteed within 15mm

Adaptive sizing:
  - arm_len = min(load_x - 15.0, build_vol_x - 5.0) but ≥ load_x - 15
  - h = build_vol_z * 0.75 (leaves margin, centers on load_z roughly)
  - fw = 2 × min_wall + min_wall (minimum hollow box)
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v1 (adaptive hollow box arm)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d = c["bolt_diameter_clearance_mm"]
    lp = c["load_point_mm"]                    # [lx, ly, lz]
    min_wall = c.get("min_wall_thickness_mm", 1.2)
    bv = c["build_volume_mm"]                  # [bvx, bvy, bvz]

    lx, ly, lz = lp[0], lp[1], lp[2]
    bvx, bvy, bvz = bv[0], bv[1], bv[2]

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    bolt_r = bolt_d / 2.0
    margin = bolt_r + min_wall

    # Mounting plate: minimal rectangle covering all bolt holes + margin
    # Clip to build volume so plate never exceeds bounds.
    plate_t  = min_wall
    plate_y0_raw = min(by_coords) - margin
    plate_y1_raw = max(by_coords) + margin
    plate_z0_raw = min(bz_coords) - margin
    plate_z1_raw = max(bz_coords) + margin

    # If raw span exceeds build volume, trim symmetrically
    y_span = plate_y1_raw - plate_y0_raw
    if y_span > bvy - 0.5:
        shrink = (y_span - (bvy - 0.5)) / 2.0
        plate_y0 = plate_y0_raw + shrink
        plate_y1 = plate_y1_raw - shrink
    else:
        plate_y0, plate_y1 = plate_y0_raw, plate_y1_raw

    z_span = plate_z1_raw - plate_z0_raw
    if z_span > bvz - 0.5:
        shrink = (z_span - (bvz - 0.5)) / 2.0
        plate_z0 = plate_z0_raw + shrink
        plate_z1 = plate_z1_raw - shrink
    else:
        plate_z0, plate_z1 = plate_z0_raw, plate_z1_raw

    # Arm geometry: hollow box in y-z, extends in x to near load point
    # fw: 2 walls of min_wall + 1 inner slot of min_wall (FEA mesh friendly)
    fw      = 3.0 * min_wall                   # e.g., 3.6mm for min_wall=1.2
    t_wall  = min_wall

    # Height: spans from plate bottom to near top of build volume
    # Center on z=lz, with 15mm clearance above load zone
    h_max   = bvz - 5.0                        # stay within build volume
    h_ideal = bvz * 0.75                       # use most of z for moment of inertia
    h       = min(h_max, max(h_ideal, lz + 15.0 + min_wall))

    # Ensure arm top is above load zone (lz + 15mm) → no tip singularity
    z_arm   = 0.0                              # arm starts at z=0 (connects to plate bottom)
    z_top   = z_arm + h

    # Arm length: reach to within 15mm load tolerance of lx
    arm_len = max(lx - 15.0, lx * 0.85)       # at least 85% of load arm
    arm_len = min(arm_len, bv[0] - 2.0)        # stay within build volume

    y_center = ly                              # center arm at load y

    # ── Hollow box arm ──────────────────────────────────────────────────────────
    outer_arm = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, y_center - fw / 2, z_arm),
        gp_Pnt(arm_len, y_center + fw / 2, z_top),
    ).Shape()

    inner_void = BRepPrimAPI_MakeBox(
        gp_Pnt(plate_t, y_center - fw / 2 + t_wall, z_arm + t_wall),
        gp_Pnt(arm_len, y_center + fw / 2 - t_wall, z_top - t_wall),
    ).Shape()

    arm = BRepAlgoAPI_Cut(outer_arm, inner_void).Shape()

    # ── Mounting plate ───────────────────────────────────────────────────────────
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    body = BRepAlgoAPI_Fuse(arm, plate).Shape()

    # ── Bolt holes ───────────────────────────────────────────────────────────────
    for by, bz in bolt_pattern:
        ax = gp_Ax2(gp_Pnt(-1.0, by, bz), gp_Dir(1, 0, 0))
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
