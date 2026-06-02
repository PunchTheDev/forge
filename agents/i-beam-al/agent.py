"""
I-beam agent for spec 002_equipment_mount (aluminum_6061).

Structural analysis:
  Material: Al6061-T6, yield = 276 MPa, density = 2.71 g/cm³
  Allowable stress: 276 / 2.5 = 110.4 MPa
  Load: 981N × 2.5 safety = 2452.5N effective at 124mm arm
  Bending moment at root: M = 981 × 2.5 × 124 = 304,290 N·mm

  Required section modulus: Z ≥ M / σ_allow = 304,290 / 110.4 = 2,757 mm³

  I-beam cross-section (h_root=80mm, flange_w=12mm, flange_t=2.5mm, web_w=2mm):
    I_flange = 2 × 12 × 2.5 × (40−1.25)² = 60 × 1500.5  = 90,034 mm⁴
    I_web    = 2 × 75³/12                                  = 70,312 mm⁴
    I_total  = 160,346 mm⁴,  c = 40mm
    Z = 160,346 / 40 = 4,009 mm³ >> 2,757 mm³ required
    σ_predict = 304,290 × 40 / 160,346 = 75.9 MPa  (68.8% of allowable, 31.2% margin)

  Build volume check: z_max = h_root = 80mm
    With plate: z from (−5.75) to 80mm = 85.75mm < 90mm build volume ✓

Mass estimate (Al density 2.71 g/cm³ = 2.71×10⁻³ g/mm³):
  Web:       124 × 2 × (75+10)/2 = 10,540 mm³ → 28.6 g
  Flanges:   2 × 124 × 12 × 2.5  =  7,440 mm³ → 20.2 g
  Plate:     91.5 × 51.5 × 3.0   = 14,147 mm³ → 38.3 g
  Bolt holes: 6 × π × 4.25² × 5  = −1,701 mm³ →  −4.6 g
  Total ≈ 82.5 g  (vs 380g baseline, −78.3%)
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for an aluminum I-beam equipment mount."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d = c["bolt_diameter_clearance_mm"]   # 8.5mm → bolt_r = 4.25mm
    lp = c["load_point_mm"]                    # [120, 50, 45]

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    bolt_r = bolt_d / 2.0
    margin = bolt_r + 1.5                       # 5.75mm structural ring

    plate_t  = 3.0
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    arm_len  = lp[0] + 4.0                     # 124mm (4mm past load point)

    web_w    = 2.0
    flange_w = 12.0
    flange_t = 2.5
    h_root   = 80.0                            # limited by build_volume_z=90mm
    h_tip    = 20.0                            # taper down at tip
    y_center = lp[1]                           # 50mm — load point y

    # ── Arm ───────────────────────────────────────────────────────────────────
    bot_flange = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, y_center - flange_w / 2, 0.0),
        gp_Pnt(arm_len, y_center + flange_w / 2, flange_t),
    ).Shape()

    web = _loft_rect(
        x0=0.0, x1=arm_len,
        y0=y_center - web_w / 2, y1=y_center + web_w / 2,
        z0_near=flange_t, z1_near=h_root - flange_t,
        z0_far=flange_t,  z1_far=h_tip - flange_t,
    )

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

    # ── Mounting plate ────────────────────────────────────────────────────────
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    fuse3 = BRepAlgoAPI_Fuse(fuse2.Shape(), plate)
    fuse3.Build()
    shape = fuse3.Shape()

    # ── Bolt holes ────────────────────────────────────────────────────────────
    for bby, bbz in bolt_pattern:
        axis = gp_Ax2(gp_Pnt(-1.0, bby, bbz), gp_Dir(1.0, 0.0, 0.0))
        hole = BRepPrimAPI_MakeCylinder(axis, bolt_r, plate_t + 2.0).Shape()
        cut_op = BRepAlgoAPI_Cut(shape, hole)
        cut_op.Build()
        shape = cut_op.Shape()

    # ── Export ────────────────────────────────────────────────────────────────
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
