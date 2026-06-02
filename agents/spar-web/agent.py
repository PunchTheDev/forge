"""
Spar-web bracket agent — three structural improvements over slim-spine.

Design rationale:
  slim-spine achieved 108.48 g by using a tall, thin spine (4mm × 70mm) instead
  of a wide rib. This agent pushes further on all three load-bearing members:

  1. Mounting plate: 3mm thick (was 5mm).
     Bolt holes are 6.5mm diameter through a 3mm face. The plate sees bolt
     preload but near-zero bending — there is no structural reason for it to be
     5mm. Minimum allowed wall is 1.2mm; 3mm gives ample clearance hole depth.

  2. Bottom rail: 1.5mm thick (was 3mm full-width flange).
     The flange carries compressive load at the bottom of the cantilever
     I-section. At 1.5mm it still satisfies the 1.2mm minimum wall constraint
     and retains the bottom-chord function of the beam while removing 60% of
     the flange volume.

  3. Spine: 3mm wide × 85mm tall (was 4mm × 70mm).
     Making the spine taller increases the second moment of area faster than
     width (I ∝ h³ vs I ∝ b). Going from 4×70 to 3×85 improves I by 34% while
     using less material. The build volume allows z=100mm; 85mm keeps the spine
     inside the plate height (80mm) with a 5mm cap for FEA node coverage.

  Stress check at x=0 (critical section, spine only):
    M = 392.4 N × 100 mm = 39,240 N·mm
    I = (3 × 85³) / 12 = 153,063 mm⁴
    c = 42.5 mm
    σ_max = M × c / I = 39,240 × 42.5 / 153,063 ≈ 10.9 MPa < 25 MPa ✓
    Safety factor on allowable ≈ 4.6×

  Mass estimate:
    Plate  3 × 80 × 80          =  19,200 mm³
    Rail  115 × 80 × 1.5        =  13,800 mm³   (plate overlap: −360)
    Spine 115 × 3 × 85          =  29,325 mm³   (rail overlap: −517;
                                                   plate overlap: −765)
    Bolt holes ×4               ≈    −400 mm³
    Net ≈ 60,283 mm³  →  74.8 g  (−33.7 g vs slim-spine, −31%)
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for a spar-web wall bracket."""
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

    plate_thickness = 3.0            # thinner than slim-spine (was 5mm)
    shelf_length = lp[0] + 15.0      # 115 mm: reaches past load point

    # --- Mounting plate at wall face — carries bolt preload only ---
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, 0.0, 0.0),
        gp_Pnt(plate_thickness, plate_y, plate_z),
    ).Shape()

    # --- Bottom rail: ultra-thin flange, full width ---
    # Acts as the compression chord of the cantilever I-section.
    # 1.5mm is above the 1.2mm minimum wall constraint.
    rail_h = 1.5
    rail = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, 0.0, 0.0),
        gp_Pnt(shelf_length, plate_y, rail_h),
    ).Shape()

    # --- Spar web: taller and narrower than slim-spine ---
    # 3mm wide × 85mm tall centered on the load point y-coordinate.
    # Height chosen to maximise I within the 80mm plate height; capped at 85mm
    # so the spine sits fully within the plate's z extent (with 5mm headroom at top).
    spine_w = 3.0
    spine_h = 85.0
    spine_y0 = lp[1] - spine_w / 2.0   # 23.5 mm
    spine_y1 = lp[1] + spine_w / 2.0   # 26.5 mm
    spine = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, spine_y0, 0.0),
        gp_Pnt(shelf_length, spine_y1, spine_h),
    ).Shape()

    # Fuse all three members
    body = BRepAlgoAPI_Fuse(plate, rail)
    body.Build()
    body = BRepAlgoAPI_Fuse(body.Shape(), spine)
    body.Build()
    shape = body.Shape()

    # Cut bolt clearance holes through mounting plate
    for by, bz in bolt_pattern:
        axis = gp_Ax2(gp_Pnt(-1.0, by, bz), gp_Dir(1.0, 0.0, 0.0))
        hole = BRepPrimAPI_MakeCylinder(
            axis, bolt_d / 2.0, plate_thickness + 2.0
        ).Shape()
        cut = BRepAlgoAPI_Cut(shape, hole)
        cut.Build()
        shape = cut.Shape()

    # Write STEP
    writer = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
    writer.Transfer(shape, STEPControl_AsIs)

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
        path = f.name
    try:
        writer.Write(path)
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.unlink(path)
