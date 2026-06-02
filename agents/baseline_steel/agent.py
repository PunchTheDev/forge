"""
Baseline stainless steel bracket for spec 003_pipe_clamp_bracket.

Parametric L-bracket: mounting plate with bolt clearance holes + horizontal
shelf reaching the load point. Reads all geometry from the spec so it adapts
to any spec. Designed with dimensions appropriate for heavy-duty stainless
brackets (thicker walls than the PLA baseline).

Estimated mass on spec 003 (stainless 316 @ 7.99 g/cm³): ~1300 g.
Miners beat this by replacing the solid shelf with thin-wall I-beam topology.
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Build a parametric stainless L-bracket and return STEP bytes."""
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
    # Back plate sized to cover all bolt holes with margin.
    plate_y = max(by_coords) + 15.0
    plate_z = max(bz_coords) + 15.0
    plate_t = 10.0

    # Arm reaches load point; must include material at the load application zone.
    lp = constraints["load_point_mm"]
    shelf_length = lp[0] + 15.0
    arm_thickness = 15.0   # thicker than the PLA baseline — suits high-load steel use
    # Position arm so its centerline passes through the load point Z coordinate.
    arm_z0 = max(0.0, lp[2] - arm_thickness / 2.0)
    arm_z1 = arm_z0 + arm_thickness

    # Mounting plate
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, 0.0, 0.0),
        gp_Pnt(plate_t, plate_y, plate_z),
    ).Shape()

    # Cantilever arm spanning the full Y width, centered on the load Z height.
    shelf = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, 0.0, arm_z0),
        gp_Pnt(shelf_length, plate_y, arm_z1),
    ).Shape()

    fused = BRepAlgoAPI_Fuse(plate, shelf)
    fused.Build()
    body = fused.Shape()

    # Bolt clearance holes through mounting plate.
    for by, bz in bolt_pattern:
        axis = gp_Ax2(gp_Pnt(-1.0, by, bz), gp_Dir(1.0, 0.0, 0.0))
        hole = BRepPrimAPI_MakeCylinder(axis, bolt_d / 2, plate_t + 2.0).Shape()
        cut = BRepAlgoAPI_Cut(body, hole)
        cut.Build()
        body = cut.Shape()

    # Write STEP.
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
