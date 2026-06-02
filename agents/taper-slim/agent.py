"""
Taper-slim bracket: aggressively tapered I-beam with proven FEA-stable wall dims.

Key insight from taper-thin (PR #29): 1.2 mm walls cause mesh-dependent results
in C3D4 linear tets — coarse vs fine mesh diverges 66 % at stress concentrations.
Proven minimum for mesh convergence: 2 mm web, 1.5 mm flanges (established by
taper-beam at 38.73 g verified).

Changes from taper-beam:
  - h_tip: 20 mm (vs 30 mm) — steeper taper follows M(x) = F*(100-x) more closely
  - flange_w: 8 mm (vs 10 mm) — narrower flanges, still below convergence threshold
  - web_w: 2 mm, flange_t: 1.5 mm — unchanged (proven safe)
  - plate: 3 mm, 4.75 mm all-round margin — unchanged (proven safe)

Structural analysis — critical section at x=0 (maximum moment):
  M      = 392.4 × 100 = 39 240 N·mm
  h_root = 90 mm,  flange_t = 1.5 mm,  web_h = 87 mm,  web_w = 2 mm
  I_web      = 2.0 × 87³ / 12                         = 109 747 mm⁴
  I_flanges  = 2 × (8 × 1.5 × 44.25²)                =  47 097 mm⁴
  I_total                                              = 156 844 mm⁴
  c = 45 mm
  σ = 39 240 × 45 / 156 844 = 11.25 MPa < 25 MPa ✓  (SF = 2.22)
      11.25 MPa < 17.5 MPa → mesh convergence not triggered

Structural analysis — midspan at x=50 mm:
  h(50) = 90 − (90−20)/108 × 50 = 57.6 mm, web_h = 54.6 mm
  I = 2×54.6³/12 + 2×(8×1.5×28.05²) = 27 152 + 18 917 = 46 069 mm⁴
  M(50) = 392.4 × 50 = 19 620 N·mm,  c = 28.8 mm
  σ = 19 620 × 28.8 / 46 069 = 12.27 MPa < 25 MPa ✓

Mass estimate (PLA, 1.24 g/cm³):
  Plate  69.5 × 69.5 × 3 − bolt holes ×4   ≈ 14 081 mm³  ( 17.5 g)
  Web    tapered h 87→17 mm, avg 52 mm × 108 × 2  ≈ 11 232 mm³  ( 13.9 g)
  Flanges 2 × (8 × 1.5 × 108)             ≈  2 592 mm³  (  3.2 g)
  Net                                       ≈ 27 905 mm³
  Mass = 27 905 × 1.24 × 10⁻³             ≈ 34.6 g

  vs taper-beam (38.73 g verified): −11 %
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for a taper-slim wall bracket."""
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

    # I-beam — proven wall dims for C3D4 mesh convergence.
    web_w    = 2.0                    # minimum for reliable C3D4 meshing
    flange_w = 8.0                    # narrowed from 10 mm; σ < 17.5 MPa ✓
    flange_t = 1.5                    # minimum for reliable C3D4 meshing

    h_root = 90.0                     # section height at wall (x=0)
    h_tip  = 20.0                     # section height at tip  (x=arm_len)

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
