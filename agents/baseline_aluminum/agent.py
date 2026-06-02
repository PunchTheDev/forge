"""
Baseline agent for spec 002_equipment_mount (aluminum_6061).

Builds a parametric aluminum L-bracket: vertical mounting plate with six M8
bolt holes + horizontal shelf reaching the load point. No topology optimization.
This is the reference score miners beat on spec 002.

Estimated mass: ~380 g. Aluminum's high specific strength means thin-walled
topology-optimized designs can cut this by 4-6x.
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Build a parametric aluminum L-bracket and return STEP bytes."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    constraints = spec["constraints"]
    bolt_pattern = constraints["bolt_pattern_mm"]
    bolt_d = constraints["bolt_diameter_clearance_mm"]

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    plate_y = max(by_coords) + 15.0
    plate_z = max(bz_coords) + 15.0
    plate_thickness = 10.0

    # Shelf extends to load point; keeps material only where structurally needed
    shelf_length = constraints["load_point_mm"][0] + 15.0
    shelf_thickness = 10.0
    shelf_z = plate_z

    # Mounting plate
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, 0.0, 0.0),
        gp_Pnt(plate_thickness, plate_y, plate_z),
    ).Shape()

    # Horizontal shelf
    shelf = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, 0.0, 0.0),
        gp_Pnt(shelf_length, shelf_z, shelf_thickness),
    ).Shape()

    fused = BRepAlgoAPI_Fuse(plate, shelf)
    fused.Build()
    body = fused.Shape()

    # M8 clearance holes through mounting plate
    for by, bz in bolt_pattern:
        axis = gp_Ax2(gp_Pnt(-1.0, by, bz), gp_Dir(1.0, 0.0, 0.0))
        hole = BRepPrimAPI_MakeCylinder(axis, bolt_d / 2, plate_thickness + 2.0).Shape()
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
