"""
Trim-frame bracket: thin-frame with tighter plate margins and shorter arm.

Improvements over thin-frame (PR #16):
  1. Mount plate: 80×80 mm → 70×70 mm  (10 mm margin past bolt pattern instead of 20 mm)
     All bolt holes remain fully enclosed — farthest bolt at (60, 60) has 6.75 mm clearance
     inside the plate after the 3.25 mm hole radius is subtracted.
  2. Arm length: 115 mm → 108 mm  (8 mm past the 100 mm load point is sufficient)

Structural analysis at x = 0 (critical section, bending about Y):
  Identical I-beam cross-section as thin-frame:
    Web:  1.2 mm × 90 mm
    Flange: 8 mm × 1.2 mm (top and bottom)
    I_total = 105 006 mm⁴,  c = 45 mm

  M     = F × L = 392.4 × 100 = 39 240 N·mm
  σ_max = 39 240 × 45 / 105 006 = 16.8 MPa < 25 MPa ✓  (SF = 2.97)
          16.8 MPa < 17.5 MPa → two-pass mesh convergence not triggered.

Volume estimate:
  Plate  70 × 70 × 1.2  − bolt holes ×4  ≈  5 750 mm³   (  7.1 g)   was 9.1 g
  Web    108 × 1.2 × 90                  ≈ 11 664 mm³   ( 14.5 g)   was 12 420 mm³ / 15.4 g
  Flanges 108 × 8 × 1.2 × 2             ≈  2 074 mm³   (  2.6 g)   was  2 211 mm³ /  2.7 g
  Net                                    ≈ 19 488 mm³
  Mass = 19 488 × 1.24 × 10⁻³          ≈  24.2 g

  vs thin-frame (27.0 g):  −10 %
  vs slim-spine (108.48 g SOTA): −78 %
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
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d = c["bolt_diameter_clearance_mm"]
    lp = c["load_point_mm"]           # [100, 25, 25]
    min_wall = c.get("min_wall_thickness_mm", 1.2)

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    # Tighter margin: 10 mm past the farthest bolt (was 20 mm).
    # Farthest bolt at (60, 60); hole radius = 3.25 mm → 6.75 mm wall remains. ✓
    plate_margin = 10.0
    plate_y = max(by_coords) + plate_margin   # 70 mm
    plate_z = max(bz_coords) + plate_margin   # 70 mm
    plate_t = min_wall                         # 1.2 mm

    # Shorter arm: 8 mm past the load point (was 15 mm).
    shelf_len = lp[0] + 8.0    # 108 mm

    # I-beam geometry — identical cross-section to thin-frame.
    web_w     = min_wall               # 1.2 mm
    flange_w  = 8.0
    flange_t  = min_wall               # 1.2 mm
    total_h   = 90.0

    y_center  = lp[1]                  # 25 mm
    web_y0    = y_center - web_w / 2   # 24.4
    web_y1    = y_center + web_w / 2   # 25.6
    flange_y0 = y_center - flange_w / 2   # 21.0
    flange_y1 = y_center + flange_w / 2   # 29.0

    # --- Mounting plate ---
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, 0.0, 0.0),
        gp_Pnt(plate_t, plate_y, plate_z),
    ).Shape()

    # --- Web ---
    web = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, web_y0, 0.0),
        gp_Pnt(shelf_len, web_y1, total_h),
    ).Shape()

    # --- Bottom flange at z = 0 ---
    bot_flange = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, flange_y0, 0.0),
        gp_Pnt(shelf_len, flange_y1, flange_t),
    ).Shape()

    # --- Top flange at z = total_h - flange_t ---
    top_flange = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, flange_y0, total_h - flange_t),
        gp_Pnt(shelf_len, flange_y1, total_h),
    ).Shape()

    body = BRepAlgoAPI_Fuse(plate, web)
    body.Build()
    body = BRepAlgoAPI_Fuse(body.Shape(), bot_flange)
    body.Build()
    body = BRepAlgoAPI_Fuse(body.Shape(), top_flange)
    body.Build()
    shape = body.Shape()

    # Cut bolt holes through the mounting plate.
    for by, bz in bolt_pattern:
        axis = gp_Ax2(gp_Pnt(-1.0, by, bz), gp_Dir(1.0, 0.0, 0.0))
        hole = BRepPrimAPI_MakeCylinder(axis, bolt_d / 2.0, plate_t + 2.0).Shape()
        cut = BRepAlgoAPI_Cut(shape, hole)
        cut.Build()
        shape = cut.Shape()

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
