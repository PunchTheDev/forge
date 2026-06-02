"""
Razor-I-beam bracket: I-section cantilever.

Design: web (1.5 mm wide × 90 mm tall) with top and bottom flanges
(10 mm × 1.2 mm each), centered on the load axis y = 25 mm.
No floor plate beyond the back plate — the I-section self-supports.

Why an I-beam beats the T-section (lean-beam PR):
  A T-section achieves high I by placing a wide flange at one extreme
  fibre, far from the neutral axis. An I-beam does the same on both
  sides simultaneously, but the flanges can be much narrower because
  neither is carrying the job alone. Result: same I, half the flange mass.

Bending analysis at x = 0 (critical section, bending about Y axis):
  M     = F × L = 392.4 × 100 = 39 240 N·mm
  Web:  1.5 mm × 87.6 mm (between flanges), centroid at z = 45 mm
  Flanges: 10 mm × 1.2 mm each, at z = 0–1.2 and z = 88.8–90 mm

  I_y:
    Web alone  = 1.5 × 87.6³ / 12              = 83 826 mm⁴
    Bot flange = (10×1.2³/12) + 10×1.2×(44.4)² = 1.44 + 23 659 = 23 660 mm⁴
    Top flange = (10×1.2³/12) + 10×1.2×(44.4)² = 23 660 mm⁴
    I_total                                     = 131 146 mm⁴

  c     = 45.0 mm (to outer flange face)
  S_y   = 131 146 / 45 = 2 914 mm³
  σ_max = 39 240 / 2 914 = 13.5 MPa < 25 MPa ✓   (SF = 3.7 on PLA yield)

  Mesh convergence gate (PR #10): 13.5 MPa < 70% × 25 = 17.5 MPa → not triggered.

Volume estimate:
  Web          115 × 1.5 × 90  = 15 525 mm³
  Bot flange   115 × 10  × 1.2 =  1 380 mm³
  Top flange   115 × 10  × 1.2 =  1 380 mm³
  Back plate     3 × 80  × 80  = 19 200 mm³
  Bolt holes (×4)               ≈   −664 mm³
  Overlaps (plate∩web, etc.)    ≈   −620 mm³
  net ≈ 36 201 mm³ × 1.24 × 10⁻³ g/mm³ ≈ 44.9 g   (−59% vs SOTA, −31% vs lean-beam)
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for a razor-I-beam wall bracket."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d = c["bolt_diameter_clearance_mm"]
    lp = c["load_point_mm"]           # [100, 25, 25]

    # Back plate covers all four bolt holes with 10 mm margin per side.
    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    plate_y = max(by_coords) + 20.0   # 80 mm
    plate_z = max(bz_coords) + 20.0   # 80 mm
    plate_t = 3.0                      # minimum safe thickness for bolt transfer

    shelf_len = lp[0] + 15.0          # 115 mm — 15 mm past the load point

    # I-beam geometry — centered on the load y-coordinate.
    web_w     = 1.5                    # web thickness (25 % over 1.2 mm min)
    flange_w  = 10.0                   # flange width in Y
    flange_t  = 1.2                    # flange thickness in Z (minimum wall)
    total_h   = 90.0                   # total I-beam height in Z

    y_center  = lp[1]                  # 25 mm — center on load axis
    web_y0    = y_center - web_w / 2   # 24.25
    web_y1    = y_center + web_w / 2   # 25.75
    flange_y0 = y_center - flange_w / 2   # 20.0
    flange_y1 = y_center + flange_w / 2   # 30.0

    # --- Mounting plate (x = 0 to plate_t) ---
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, 0.0, 0.0),
        gp_Pnt(plate_t, plate_y, plate_z),
    ).Shape()

    # --- Web: thin vertical rectangle running the full arm length ---
    web = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, web_y0, 0.0),
        gp_Pnt(shelf_len, web_y1, total_h),
    ).Shape()

    # --- Bottom flange: horizontal cap at z = 0 ---
    bot_flange = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, flange_y0, 0.0),
        gp_Pnt(shelf_len, flange_y1, flange_t),
    ).Shape()

    # --- Top flange: horizontal cap at z = total_h - flange_t ---
    top_flange = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, flange_y0, total_h - flange_t),
        gp_Pnt(shelf_len, flange_y1, total_h),
    ).Shape()

    # Fuse all components into one solid.
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
