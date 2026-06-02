"""
Trim-frame bracket: thin-frame with tighter plate margins and shorter arm.

Improvements over thin-frame (PR #16):
  1. Mount plate: 80×80 mm → ~74×74 mm
     Positive margin: 10 mm past the farthest bolt (y=60, z=60) → 70 mm
     Negative margin: bolt_r + 1 mm clearance past bolts at y=0, z=0 → ~-4.25 mm origin
     All bolt holes remain fully enclosed.
  2. Arm length: 115 mm → 108 mm  (8 mm past the 100 mm load point is sufficient)

Structural analysis at x = 0 (critical section, bending about Y):
  Identical I-beam cross-section as thin-frame:
    Web:  1.2 mm × 90 mm
    Flange: 8 mm × 1.2 mm (top and bottom)
    I_total = 105 006 mm⁴,  c = 45 mm

  M     = F × L = 392.4 × 100 = 39 240 N·mm
  σ_max = 39 240 × 45 / 105 006 = 16.8 MPa < 25 MPa ✓  (SF = 2.97)
          16.8 MPa < 17.5 MPa → two-pass mesh convergence not triggered.

Geometry notes:
  - Plate origin offset -4.25 mm in y and z so all four bolt holes are fully inside.
  - Components are NON-OVERLAPPING touching solids; web/flanges start at x=plate_t.
  - ShapeFix run before STEP Transfer to heal any tolerance issues from Boolean ops.
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for a trim-frame wall bracket."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.ShapeFix import ShapeFix_Shape
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d = c["bolt_diameter_clearance_mm"]
    lp = c["load_point_mm"]           # [100, 25, 25]
    min_wall = c.get("min_wall_thickness_mm", 1.2)

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]

    plate_t = min_wall                 # 1.2 mm
    bolt_r  = bolt_d / 2.0            # 3.25 mm

    # Positive margin: 10 mm past the farthest bolt center.
    plate_margin = 10.0
    plate_y1 = max(by_coords) + plate_margin   # 70 mm
    plate_z1 = max(bz_coords) + plate_margin   # 70 mm

    # Negative margin: bolt_r + 1 mm clearance so every bolt hole is fully inside.
    # Without this the corner bolts at y=0, z=0 produce partial arcs that crash
    # the OCC STEP Transfer (degenerate face at the plate edge).
    plate_y0 = min(by_coords) - bolt_r - 1.0   # ~-4.25 mm
    plate_z0 = min(bz_coords) - bolt_r - 1.0   # ~-4.25 mm

    # Shorter arm: 8 mm past the load point (was 15 mm).
    arm_x = lp[0] + 8.0    # 108 mm (total bracket depth)

    # I-beam geometry.
    web_w     = min_wall               # 1.2 mm
    flange_w  = 8.0
    flange_t  = min_wall               # 1.2 mm
    total_h   = 90.0

    y_center  = lp[1]                  # 25 mm
    web_y0    = y_center - web_w / 2   # 24.4
    web_y1    = y_center + web_w / 2   # 25.6
    flange_y0 = y_center - flange_w / 2   # 21.0
    flange_y1 = y_center + flange_w / 2   # 29.0

    # Build four NON-OVERLAPPING solids that TOUCH at their boundaries.
    # This avoids degenerate thin-wall Boolean intersections that crash OCC.

    # --- Mounting plate: x=[0, plate_t], y=[plate_y0, plate_y1], z=[plate_z0, plate_z1] ---
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    # --- Web: starts at x=plate_t (touches plate, no overlap)
    #          z spans only the space between flanges ---
    web = BRepPrimAPI_MakeBox(
        gp_Pnt(plate_t, web_y0, flange_t),
        gp_Pnt(arm_x, web_y1, total_h - flange_t),
    ).Shape()

    # --- Bottom flange: z=[0, flange_t], starts at x=plate_t ---
    bot_flange = BRepPrimAPI_MakeBox(
        gp_Pnt(plate_t, flange_y0, 0.0),
        gp_Pnt(arm_x, flange_y1, flange_t),
    ).Shape()

    # --- Top flange: z=[total_h-flange_t, total_h], starts at x=plate_t ---
    top_flange = BRepPrimAPI_MakeBox(
        gp_Pnt(plate_t, flange_y0, total_h - flange_t),
        gp_Pnt(arm_x, flange_y1, total_h),
    ).Shape()

    # Fuse all four touching components.
    # Explicit intermediate variables avoid pybind11 lifetime issues.
    fuse1 = BRepAlgoAPI_Fuse(plate, web)
    fuse1.Build()
    s1 = fuse1.Shape()

    fuse2 = BRepAlgoAPI_Fuse(s1, bot_flange)
    fuse2.Build()
    s2 = fuse2.Shape()

    fuse3 = BRepAlgoAPI_Fuse(s2, top_flange)
    fuse3.Build()
    shape = fuse3.Shape()

    # Cut bolt holes through the mounting plate.
    cut_ops = []   # keep alive to prevent GC during loop
    for by, bz in bolt_pattern:
        axis = gp_Ax2(gp_Pnt(-1.0, by, bz), gp_Dir(1.0, 0.0, 0.0))
        hole = BRepPrimAPI_MakeCylinder(axis, bolt_r, plate_t + 2.0).Shape()
        cut_op = BRepAlgoAPI_Cut(shape, hole)
        cut_op.Build()
        cut_ops.append(cut_op)
        shape = cut_op.Shape()

    # Heal shape before STEP Transfer: Boolean ops on complex/thin geometry can
    # leave small tolerance violations that crash the STEP writer with SIGSEGV.
    fixer = ShapeFix_Shape(shape)
    fixer.Perform()
    shape = fixer.Shape()

    # Write STEP.
    writer = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP203")
    writer.Transfer(shape, STEPControl_AsIs)

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
        path = f.name
    try:
        writer.Write(path)
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.unlink(path)
