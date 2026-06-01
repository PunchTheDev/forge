"""
Slim-spine bracket agent — tall thin web for maximum bending efficiency.

Design rationale:
  For a cantilever loaded in -Z at x=100mm, the critical section at the wall
  (x=0) carries M = F × L = 392.4 × 100 = 39,240 N·mm.

  Bending section modulus: S = I / c = (b × h³ / 12) / (h/2) = b × h² / 6.
  Since S scales with h², doubling height halves the required width.

  The ribbed agent uses a 12mm × 35mm web → S = 12 × 35² / 6 = 2,450 mm³.
  This agent uses a 4mm × 70mm web → S = 4 × 70² / 6 = 3,267 mm³ (+33% stronger).

  Same strength, but far less material:
    Old: 12 × 35 = 420 mm² cross-section area
    New:  4 × 70 = 280 mm² cross-section area (−33%)

  Stress check (wall section, x=0):
    I = 4 × 70³ / 12 = 114,333 mm⁴
    σ_max = M × c / I = 39,240 × 35 / 114,333 ≈ 12.0 MPa < 25 MPa ✓  (SF≈4.2)

  Estimated mass vs ribbed (~155 g):
    Plate  5 × 80 × 80          =  32,000 mm³
    Flange 115 × 80 × 3         =  27,600 mm³   (overlap with plate: −1,200)
    Spine  115 × 4 × 70         =  32,200 mm³   (overlap with flange: −1,380;
                                                   overlap with plate:  −1,400)
    Bolt holes ×4               ≈  −    663 mm³
    Net ≈ 87,157 mm³  →  108 g  (−47 g vs ribbed, −23%)
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for a slim-spine wall bracket."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d = c["bolt_diameter_clearance_mm"]
    lp = c["load_point_mm"]          # [100, 25, 25]

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    plate_y = max(by_coords) + 20.0  # 80 mm
    plate_z = max(bz_coords) + 20.0  # 80 mm
    plate_thickness = 5.0

    shelf_length = lp[0] + 15.0      # 115 mm

    # --- Mounting plate (at wall face, provides all 4 bolt holes) ---
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, 0.0, 0.0),
        gp_Pnt(plate_thickness, plate_y, plate_z),
    ).Shape()

    # --- Bottom flange: thin slab connecting z=0 bolt row to spine base ---
    flange_h = 3.0
    flange = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, 0.0, 0.0),
        gp_Pnt(shelf_length, plate_y, flange_h),
    ).Shape()

    # --- Spine: tall narrow web centered on the load point (y=25) ---
    # Tall height → high second moment of area, allowing very thin width.
    # z=0 to z=70mm (limited by build volume z=100, with margin for the plate z=80).
    spine_w = 4.0
    spine_h = 70.0
    spine_y0 = lp[1] - spine_w / 2.0   # 23 mm
    spine_y1 = lp[1] + spine_w / 2.0   # 27 mm
    spine = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, spine_y0, 0.0),
        gp_Pnt(shelf_length, spine_y1, spine_h),
    ).Shape()

    # Fuse all three components
    body = BRepAlgoAPI_Fuse(plate, flange)
    body.Build()
    body = BRepAlgoAPI_Fuse(body.Shape(), spine)
    body.Build()
    shape = body.Shape()

    # Cut bolt holes through the mounting plate
    for by, bz in bolt_pattern:
        axis = gp_Ax2(gp_Pnt(-1.0, by, bz), gp_Dir(1.0, 0.0, 0.0))
        hole = BRepPrimAPI_MakeCylinder(axis, bolt_d / 2.0, plate_thickness + 2.0).Shape()
        cut = BRepAlgoAPI_Cut(shape, hole)
        cut.Build()
        shape = cut.Shape()

    # Write STEP
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
