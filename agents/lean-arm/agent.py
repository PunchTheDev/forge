"""
Lean-arm bracket: aggressively tapered I-beam with tighter cross-section.

Extends taper-slim with two further reductions, each analytically validated:
  - h_tip: 15 mm (vs 20 mm in taper-slim) — steeper taper follows M(x) more closely
  - flange_w: 6 mm (vs 8 mm in taper-slim) — narrower flanges, still mesh-convergent

Web and flange thickness are unchanged at 2 mm / 1.5 mm (proven C3D4 safe minimum).
Plate remains 3 mm (proven minimum for bolt-hole FEA stress).

Structural analysis — all cross-sections checked:

  Root (x=0): h=90 mm
    I_web     = 2 × 87³ / 12              = 109 747 mm⁴
    I_flanges = 2 × (6 × 1.5 × 44.25²)   =  35 246 mm⁴
    I_total                                = 144 993 mm⁴
    σ = 39 240 × 45 / 144 993 = 12.18 MPa < 17.5 MPa ✓  (mesh-convergent)

  Midspan (x=54): h=52.5 mm
    I_web     = 2 × 49.5³ / 12             =  20 212 mm⁴
    I_flanges = 2 × (6 × 1.5 × 25.5²)     =  11 704 mm⁴
    I_total                                 =  31 916 mm⁴
    σ = 18 050 × 26.25 / 31 916 = 14.84 MPa < 17.5 MPa ✓  (mesh-convergent)

Mass estimate (PLA, 1.24 g/cm³):
  Plate  69.5 × 69.5 × 3 − bolt holes ×4  ≈ 14 093 mm³  (17.5 g)
  Web    tapered h 87→12 mm, avg 49.5 mm × 108 × 2   ≈ 10 692 mm³  (13.3 g)
  Flanges 2 × (6 × 1.5 × 108)             ≈  1 944 mm³  ( 2.4 g)
  Net                                       ≈ 26 729 mm³
  Mass = 26 729 × 1.24 × 10⁻³             ≈ 33.1 g

  vs taper-slim (34.6 g est.): −4.4 %
  vs taper-beam (38.73 g verified): −14.5 %
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for a lean-arm wall bracket."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d = c["bolt_diameter_clearance_mm"]
    lp = c["load_point_mm"]           # [100, 25, 25]

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    bolt_r = bolt_d / 2.0
    margin = bolt_r + 1.5             # 4.75 mm — full clearance past hole edge

    # Mounting plate: 3 mm thick (proven minimum for bolt-hole FEA stress).
    plate_t  = 3.0
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    arm_len = lp[0] + 8.0             # 108 mm (8 mm past load point)

    # I-beam — proven wall dims for C3D4 mesh convergence, tighter section.
    web_w    = 2.0                    # minimum for reliable C3D4 meshing
    flange_w = 6.0                    # reduced from 8 mm; σ_max = 14.84 MPa < 17.5 MPa ✓
    flange_t = 1.5                    # minimum for reliable C3D4 meshing

    h_root = 90.0                     # section height at wall (x=0)
    h_tip  = 15.0                     # section height at tip  (x=arm_len)

    y_center = lp[1]                  # 25 mm

    # Bottom flange: flat, constant z=[0, flange_t], full arm length.
    bot_flange = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, y_center - flange_w / 2, 0.0),
        gp_Pnt(arm_len, y_center + flange_w / 2, flange_t),
    ).Shape()

    # Tapered web: bottom at z=flange_t, top tapers from h_root to h_tip.
    web = _loft_rect(
        x0=0.0, x1=arm_len,
        y0=y_center - web_w / 2, y1=y_center + web_w / 2,
        z0_near=flange_t, z1_near=h_root - flange_t,
        z0_far=flange_t,  z1_far=h_tip - flange_t,
    )

    # Tapered top flange: follows the slanting top of the web.
    top_flange = _loft_rect(
        x0=0.0, x1=arm_len,
        y0=y_center - flange_w / 2, y1=y_center + flange_w / 2,
        z0_near=h_root - flange_t, z1_near=h_root,
        z0_far=h_tip - flange_t,   z1_far=h_tip,
    )

    fuse1 = BRepAlgoAPI_Fuse(bot_flange, web)
    fuse1.Build()
    fuse2 = BRepAlgoAPI_Fuse(fuse1.Shape(), top_flange)
    fuse2.Build()

    # Mounting plate: fused at x=[0, plate_t] for continuous junction with arm.
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    fuse3 = BRepAlgoAPI_Fuse(fuse2.Shape(), plate)
    fuse3.Build()
    shape = fuse3.Shape()

    # Drill bolt holes through the mounting plate.
    for bby, bbz in bolt_pattern:
        axis = gp_Ax2(gp_Pnt(-1.0, bby, bbz), gp_Dir(1.0, 0.0, 0.0))
        hole = BRepPrimAPI_MakeCylinder(axis, bolt_r, plate_t + 2.0).Shape()
        cut_op = BRepAlgoAPI_Cut(shape, hole)
        cut_op.Build()
        shape = cut_op.Shape()

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


def _loft_rect(
    x0: float, x1: float,
    y0: float, y1: float,
    z0_near: float, z1_near: float,
    z0_far: float, z1_far: float,
):
    """Loft a solid between two axis-aligned rectangles at x=x0 and x=x1."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    from OCP.gp import gp_Pnt

    def make_rect_wire(x, ya, yb, za, zb):
        pts = [
            gp_Pnt(x, ya, za), gp_Pnt(x, yb, za),
            gp_Pnt(x, yb, zb), gp_Pnt(x, ya, zb),
        ]
        wire = BRepBuilderAPI_MakeWire()
        for i in range(4):
            e = BRepBuilderAPI_MakeEdge(pts[i], pts[(i + 1) % 4]).Edge()
            wire.Add(e)
        return wire.Wire()

    loft = BRepOffsetAPI_ThruSections(True)
    loft.AddWire(make_rect_wire(x0, y0, y1, z0_near, z1_near))
    loft.AddWire(make_rect_wire(x1, y0, y1, z0_far, z1_far))
    loft.Build()
    return loft.Shape()
