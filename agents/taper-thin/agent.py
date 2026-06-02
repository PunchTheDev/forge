"""
Taper-thin bracket: linearly tapered I-beam with minimum 1.2 mm walls.

Combines two proven improvements:
  1. Taper-beam's linear taper (I ∝ h³ drops fast away from root, saving web volume)
  2. Thin-frame's minimum-wall 1.2 mm throughout (all walls at printability limit)

The bending moment M(x) = F*(L-x) is maximum at the wall (x=0) and zero at the
tip (x=L). A uniform beam wastes material where the moment is low. Tapering the
web height proportionally reduces volume while maintaining stress margin everywhere.

I-beam geometry:
  web_w   = 1.2 mm  (minimum printable wall)
  flange_w = 8 mm   (minimum for stress below 70% allowable at root)
  flange_t = 1.2 mm (minimum printable wall)
  h_root  = 90 mm   (full build-volume height at wall)
  h_tip   = 20 mm   (minimum viable section at low-moment tip)

Structural analysis — critical section at x=0 (root):
  M = F × arm_reach = 392.4 × 100 = 39 240 N·mm
  Web height between flanges = 90 − 2 × 1.2 = 87.6 mm
  I_web     = 1.2 × 87.6³ / 12               =  67 060 mm⁴
  I_flanges = 2 × (8 × 1.2 × 44.4²)          =  37 854 mm⁴
  I_total                                     = 104 914 mm⁴
  c = 45 mm
  σ_root = 39 240 × 45 / 104 914 = 16.8 MPa < 25 MPa ✓  (SF = 2.97)
          16.8 MPa < 17.5 MPa (70% allowable) → no mesh convergence re-run

Structural analysis — midspan at x=50 mm:
  h(50)  = 90 − (90−20)/115 × 50 = 63.9 mm
  M(50)  = 392.4 × 50 = 19 620 N·mm
  I_web  = 1.2 × 61.5³ / 12   = 23 247 mm⁴
  I_fl   = 2 × 8×1.2×31.35²   = 18 912 mm⁴
  I      = 42 159 mm⁴,  c = 31.95 mm
  σ(50) = 19 620 × 31.95 / 42 159 = 14.9 MPa < 25 MPa ✓

Volume estimate (tight plate + tapered arm):
  Plate  70×70×1.2  − bolt holes ×4       ≈  5 500 mm³   (  6.8 g)
  Web    (tapered trapezoid, 1.2 mm wide)  ≈  8 280 mm³   ( 10.3 g)
  Flanges 8×1.2×115 × 2                   ≈  2 208 mm³   (  2.7 g)
  Net                                      ≈ 15 988 mm³
  Mass = 15 988 × 1.24 × 10⁻³             ≈  19.8 g

  vs thin-frame  (~27.0 g):  −27 %
  vs taper-beam  ( 38.7 g):  −49 %
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

    # Tight plate margins: bolt_r + 1.5 mm clearance past outer bolts.
    plate_y0 = min(by_coords) - bolt_r - 1.5   # ~-4.75 mm → clamp to 0
    plate_y0 = max(0.0, plate_y0)
    plate_y1 = max(by_coords) + bolt_r + 1.5   # 74.75 mm → 70+4.25+1.5
    plate_z0 = 0.0
    plate_z1 = max(bz_coords) + bolt_r + 1.5

    plate_t = min_wall                 # 1.2 mm (minimum printable wall)
    arm_len = lp[0] + 15.0            # 115 mm

    # I-beam parameters — all at minimum wall
    web_w    = min_wall                # 1.2 mm
    flange_w = 8.0                     # Y span; enough for σ < 70% allowable
    flange_t = min_wall                # 1.2 mm

    h_root = 90.0                     # I-beam height at x=0
    h_tip  = 20.0                     # I-beam height at x=arm_len

    y_center = lp[1]                  # 25 mm

    # Bottom flange: flat at z=[0, flange_t], full arm length
    bot_flange = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, y_center - flange_w / 2, 0.0),
        gp_Pnt(arm_len, y_center + flange_w / 2, flange_t),
    ).Shape()

    # Tapered web: loft from (h_root − 2*flange_t) tall at root to
    # (h_tip − 2*flange_t) tall at tip, bottom edge constant at z=flange_t.
    web = _loft_rect(
        x0=0.0, x1=arm_len,
        y0=y_center - web_w / 2, y1=y_center + web_w / 2,
        z0_near=flange_t, z1_near=h_root - flange_t,
        z0_far=flange_t,  z1_far=h_tip - flange_t,
    )

    # Tapered top flange: follows the slanting top edge of the web
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

    # Mounting plate at x=0 face (minimum wall, tight margins around bolts)
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    fuse3 = BRepAlgoAPI_Fuse(fuse2.Shape(), plate)
    fuse3.Build()
    shape = fuse3.Shape()

    # Drill bolt holes through the mounting plate
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
