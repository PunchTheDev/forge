"""
Ribbed bracket agent — first structural optimization over the naive baseline.

Design rationale:
  The naive L-bracket uses a solid 115×80×12mm shelf slab (~110k mm³).
  For a 40 kg cantilever load at 100mm reach, the dominant mode is bending
  about the horizontal axis at the wall. An I-beam/ribbed cross-section carries
  that bending with far less material than a solid slab.

  This design uses:
    1. A thin bottom flange (5mm) spanning the full bracket width — connects
       the mounting plate to the load tip and provides a flat print base.
    2. A central load rib (12mm wide × 35mm tall) running wall-to-tip, centered
       on the load point (y=25, z=0..35). The rib keeps max bending stress
       well below the 25 MPa allowable (yield/SF=50/2).
    3. Mounting plate reduced from 10mm to 7mm.

  Hand check (wall section, x=0):
    M = 392.4 N × 100 mm = 39 240 N·mm
    I_rib = 12 × 35³ / 12 = 42 875 mm⁴
    σ_max = M × (35/2) / I_rib = 39 240 × 17.5 / 42 875 ≈ 16 MPa < 25 MPa ✓

  Expected mass (vs baseline ~202 g):
    Plate 7×80×80  =  44 800 mm³
    Flange 115×80×5 =  46 000 mm³   (overlap with plate: −7×80×5 = −2 800)
    Rib 115×12×35  =  48 300 mm³   (overlap with flange: −115×12×5 = −6 900;
                                     overlap with plate:  −7×12×35 = −2 940;
                                     plate+flange corner: +7×12×5  = +420)
    Bolt holes ×4   = −1 550 mm³
    Net ≈ 125 330 mm³  →  155 g  (−47 g vs baseline)
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for a ribbed wall bracket."""
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
    plate_thickness = 7.0

    shelf_length = lp[0] + 15.0      # 115 mm

    # 1. Mounting plate (back wall)
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, 0.0, 0.0),
        gp_Pnt(plate_thickness, plate_y, plate_z),
    ).Shape()

    # 2. Bottom flange — thin horizontal slab, full width, full reach
    flange_h = 5.0
    flange = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, 0.0, 0.0),
        gp_Pnt(shelf_length, plate_y, flange_h),
    ).Shape()

    # 3. Central load rib — tall and narrow, centered on load point y=25
    rib_w = 12.0
    rib_h = lp[2] + 10.0             # 35 mm (load point z=25 + 10 mm headroom)
    rib_y0 = lp[1] - rib_w / 2.0    # 19 mm
    rib_y1 = lp[1] + rib_w / 2.0    # 31 mm
    rib = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, rib_y0, 0.0),
        gp_Pnt(shelf_length, rib_y1, rib_h),
    ).Shape()

    # Fuse plate + flange + rib
    body = BRepAlgoAPI_Fuse(plate, flange)
    body.Build()
    body = BRepAlgoAPI_Fuse(body.Shape(), rib)
    body.Build()
    shape = body.Shape()

    # Cut bolt holes through mounting plate
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
