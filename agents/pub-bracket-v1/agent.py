"""
pub-bracket-v1: Parametric hollow-box cantilever bracket for pub specs.

Reads all constraints from spec dynamically. Works for PLA, PETG, Al6061.

Design: hollow box arm + minimal mounting plate.
  - Arm: fw=3×min_wall wide, h=build_vol_z×0.75 tall, extends to load x
  - Wall thickness: min_wall on all sides
  - Arm length: min(load_x - load_tol, build_vol_x) where load_tol=15mm
  - Load nodes: arm covers z=load_z±(h/2), guaranteed within 15mm

Adaptive sizing:
  - arm_len = min(load_x - 15.0, build_vol_x - 5.0) but ≥ load_x - 15
  - h = build_vol_z * 0.75 (leaves margin, centers on load_z roughly)
  - fw = 3 × min_wall (minimum hollow box)

Plate margin:
  - Ideal = bolt_r + min_wall on each side of bolt pattern
  - If bolt pattern is close to build volume edge and the resulting sliver
    between bolt hole and plate edge would be < 0.5 mm (causing surface-mesh
    PLC errors in tetgen), pull the plate edge back so the bolt hole creates
    a clean U-notch instead of a thin sliver.
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

    bolt_y_span = max(by_coords) - min(by_coords)
    bolt_z_span = max(bz_coords) - min(bz_coords)

    # Available space on each side of the bolt pattern within build volume
    # (keep 0.5 mm safety gap from the build volume edge itself)
    y_half_avail = (bvy - bolt_y_span) / 2.0 - 0.5
    z_half_avail = (bvz - bolt_z_span) / 2.0 - 0.5

    ideal_margin = bolt_r + min_wall   # structural clearance around each hole

    margin_y = min(ideal_margin, max(0.0, y_half_avail))
    margin_z = min(ideal_margin, max(0.0, z_half_avail))

    # When clipping forces the plate edge within 0.5 mm of a bolt hole edge,
    # the surface mesher (gmsh/tetgen) fails with a PLC intersection error.
    # Fix: pull the edge back to 0.5 mm INSIDE the bolt hole → clean U-notch.
    MIN_SLIVER = 0.5
    if 0.0 < margin_y - bolt_r < MIN_SLIVER:
        margin_y = bolt_r - MIN_SLIVER
    if 0.0 < margin_z - bolt_r < MIN_SLIVER:
        margin_z = bolt_r - MIN_SLIVER

    # Mounting plate extents (no separate clipping step needed — margin already fits)
    plate_t  = min_wall
    plate_y0 = min(by_coords) - margin_y
    plate_y1 = max(by_coords) + margin_y
    plate_z0 = min(bz_coords) - margin_z
    plate_z1 = max(bz_coords) + margin_z

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
