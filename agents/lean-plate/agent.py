"""
Lean-plate bracket: lean-arm with 2.75mm plate (vs 3mm) and 104mm arm.

The lean-arm mounting plate is 17.5 g out of 32.64 g total. Reducing plate
thickness from 3.0 mm to 2.75 mm reduces plate mass by 8.3% → ~1.5 g savings.

Bolt-hole bearing stress scales with 1/plate_t:
  σ_bearing = F_bolt / (2 × bolt_r × plate_t)
  At plate_t=3.0:  σ ≈ 17.05 MPa (FEA-verified lean-arm SOTA)
  At plate_t=2.75: σ = 17.05 × (3.0/2.75) = 18.60 MPa < 25.0 MPa ✓  (26% headroom)

Minimum wall check:
  Ring width = margin − bolt_r = 4.75 − 3.25 = 1.50 mm (unchanged)
  Plate thickness at ring = 2.75 mm > 1.2 mm minimum ✓

Mass estimate (PLA, 1.24 g/cm³):
  Plate reduction: 69.5 × 69.5 × 0.25 − 4 × π × 3.25² × 0.25 ≈ 1207 − 83 = 1124 mm³ → 1.39 g
  Arm shortening (104 mm vs 108 mm): ~0.56 g
  Total savings: ~1.95 g
  Estimated mass: 32.64 − 1.95 ≈ 30.69 g
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for a lean-plate wall bracket."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d = c["bolt_diameter_clearance_mm"]
    lp = c["load_point_mm"]

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    bolt_r = bolt_d / 2.0
    margin = bolt_r + 1.5

    # Plate: 2.75 mm (reduced from 3.0 mm; bearing stress = 18.60 MPa < 25 MPa)
    plate_t  = 2.75
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    arm_len = lp[0] + 4.0             # 104 mm

    web_w    = 2.0
    flange_w = 6.0
    flange_t = 1.5
    h_root   = 90.0
    h_tip    = 15.0
    y_center = lp[1]

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

    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    fuse3 = BRepAlgoAPI_Fuse(fuse2.Shape(), plate)
    fuse3.Build()
    shape = fuse3.Shape()

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


def _loft_rect(x0, x1, y0, y1, z0_near, z1_near, z0_far, z1_far):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    from OCP.gp import gp_Pnt

    def make_rect_wire(x, ya, yb, za, zb):
        pts = [gp_Pnt(x, ya, za), gp_Pnt(x, yb, za), gp_Pnt(x, yb, zb), gp_Pnt(x, ya, zb)]
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
