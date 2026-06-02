"""
Taper-thin bracket: tapered I-beam arm with all arm walls at minimum 1.2 mm.

Combines two proven improvements:
  1. Thin arm walls — web and flanges at 1.2 mm (vs 2 mm + 1.5 mm in taper-beam)
  2. Linear arm taper — web height drops from 90 mm at root to 20 mm at tip,
     matching the bending moment diagram M(x) = F*(L-x)

Plate stays at 3 mm (proven minimum from taper-beam) because C3D4 mesh
around M8 bolt holes at 1.2 mm plate thickness concentrates above allowable.
The arm accounts for most of the mass reduction vs taper-beam.

I-beam geometry:
  web_w    = 1.2 mm  (minimum printable wall)
  flange_w = 8 mm    (minimum for σ < 70% allowable at root)
  flange_t = 1.2 mm  (minimum printable wall)
  h_root   = 90 mm   (full available build-volume height at x=0)
  h_tip    = 20 mm   (minimum viable section at low-moment tip)

Structural analysis — critical section at root (x=0):
  M = F × arm_reach = 392.4 × 100 = 39 240 N·mm
  Web height between flanges = 90 − 2 × 1.2 = 87.6 mm
  I_web     = 1.2 × 87.6³ / 12               =  67 060 mm⁴
  I_flanges = 2 × (8 × 1.2 × 44.4²)          =  37 854 mm⁴
  I_total                                     = 104 914 mm⁴
  c = 45 mm
  σ_root = 39 240 × 45 / 104 914 = 16.8 MPa < 25 MPa ✓  (SF = 2.97)
          16.8 MPa < 17.5 MPa → no mesh convergence re-run

Structural analysis — midspan (x=50 mm):
  h(50) = 90 − (90−20)/115 × 50 = 63.9 mm
  M(50) = 392.4 × 50 = 19 620 N·mm
  I     = 42 159 mm⁴,  c = 31.95 mm
  σ(50) = 14.9 MPa < 25 MPa ✓

Volume estimate:
  Plate  69.5×69.5×3  − bolt holes ×4        ≈ 14 081 mm³  ( 17.5 g)
  Web    tapered trapezoid, 1.2 mm wide       ≈  7 590 mm³  (  9.4 g)
  Flanges 8×1.2×115 × 2                      ≈  2 208 mm³  (  2.7 g)
  Net                                         ≈ 23 879 mm³
  Mass = 23 879 × 1.24 × 10⁻³                ≈  29.6 g

  vs taper-beam ( 38.7 g verified):  −23 %
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for a taper-thin wall bracket."""
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
    bolt_r = bolt_d / 2.0
    margin = bolt_r + 1.5            # 1.5 mm clearance beyond hole edge

    # Plate: 3 mm (minimum proven thickness for C3D4 bolt-hole FEA).
    # Extends margin past every bolt hole on all four sides.
    plate_t  = 3.0
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    arm_len = lp[0] + 15.0            # 115 mm (15 mm past load point)

    # Arm I-beam — all walls at minimum printable thickness.
    web_w    = min_wall                # 1.2 mm
    flange_w = 8.0                    # Y span; enough for σ < 70% allowable
    flange_t = min_wall                # 1.2 mm

    h_root = 90.0                     # web height at x=0
    h_tip  = 20.0                     # web height at x=arm_len

    y_center = lp[1]                  # 25 mm

    # Bottom flange: flat at z=[0, flange_t], full arm length.
    bot_flange = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, y_center - flange_w / 2, 0.0),
        gp_Pnt(arm_len, y_center + flange_w / 2, flange_t),
    ).Shape()

    # Tapered web: constant bottom at z=flange_t, top tapers from h_root to h_tip.
    web = _loft_rect(
        x0=0.0, x1=arm_len,
        y0=y_center - web_w / 2, y1=y_center + web_w / 2,
        z0_near=flange_t, z1_near=h_root - flange_t,
        z0_far=flange_t,  z1_far=h_tip - flange_t,
    )

    # Tapered top flange: follows the slanting top edge of the web.
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
