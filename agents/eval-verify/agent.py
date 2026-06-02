"""
Pipeline verification agent — adaptive L-bracket for all 3 rounds.

Generates a valid bracket for any spec in rounds 1-3. Not optimized
for any metric — purpose is to verify the multi-spec pool eval and CI
pipeline work correctly for mass, stiffness-to-weight, and deflection.

Close this PR without merging after CI passes all 3 categories.
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Build a parametric L-bracket that fits any spec's constraints."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bv = c["build_volume_mm"]       # [x, y, z] max extents
    bolts = c["bolt_pattern_mm"]    # [[y, z], ...] on mount face
    bolt_d = c["bolt_diameter_clearance_mm"]
    load_pt = c["load_point_mm"]    # [x, y, z]

    bvx, bvy, bvz = bv[0], bv[1], bv[2]

    # Bolt extents — clamp plate dimensions to build volume
    bolt_ys = [b[0] for b in bolts]
    bolt_zs = [b[1] for b in bolts]
    by_max = max(bolt_ys)
    bz_max = max(bolt_zs)

    plate_t = min(12.0, bvx * 0.08)
    plate_y = min(bvy - 2.0, by_max + 12.0)   # clamped to build volume Y
    plate_z = min(bvz - 2.0, bz_max + 12.0)   # clamped to build volume Z

    # Shelf: extends from plate to past load point, stays within build volume
    shelf_len = min(bvx - plate_t - 2.0, load_pt[0] + 10.0)
    shelf_h = min(plate_z, bvz * 0.8)
    shelf_t = min(15.0, bvz * 0.15, plate_z * 0.2)

    # Mounting plate
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, 0.0, 0.0),
        gp_Pnt(plate_t, plate_y, plate_z),
    ).Shape()

    # Horizontal shelf
    shelf = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, 0.0, 0.0),
        gp_Pnt(plate_t + shelf_len, plate_y, shelf_t),
    ).Shape()

    fused = BRepAlgoAPI_Fuse(plate, shelf)
    fused.Build()
    body = fused.Shape()

    # Bolt clearance holes through mounting plate
    for by, bz in bolts:
        by_c = min(max(by, bolt_d / 2 + 1), plate_y - bolt_d / 2 - 1)
        bz_c = min(max(bz, bolt_d / 2 + 1), plate_z - bolt_d / 2 - 1)
        axis = gp_Ax2(gp_Pnt(-1.0, by_c, bz_c), gp_Dir(1.0, 0.0, 0.0))
        hole = BRepPrimAPI_MakeCylinder(axis, bolt_d / 2, plate_t + 2.0).Shape()
        cut = BRepAlgoAPI_Cut(body, hole)
        cut.Build()
        body = cut.Shape()

    # Write STEP
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
