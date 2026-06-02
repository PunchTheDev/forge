"""
Slim-beam bracket: deep-pocket + reduced arm height.

Two independent stress pools from deep-pocket FEA data (29.15g, 13.3 MPa):

  1. Arm bending (critical at h_root, x≈0):
       - Arm bending stress in deep-pocket ≈ σ_arm (same geometry as pocket-plate)
       - pocket-plate arm stress = 12.6 MPa (arm was critical then, pocket was not)
       - Reducing h_root from 90→84mm changes I:
           Old I ≈ 2×9×(45−0.75)² + 2×(87)³/12 = 35,235 + 109,734 = 144,969 mm⁴, c=45
           New I ≈ 2×9×(42−0.75)² + 2×(81)³/12 = 30,532 + 88,574 = 119,106 mm⁴, c=42
           σ_arm_new = 12.6 × (42/119,106) / (45/144,969) = 12.6 × 1.137 = 14.3 MPa

  2. Pocket zone (now critical in deep-pocket):
       - Back-calc from deep-pocket: σ_unpocketed = 13.3 / (3/1.8)² = 4.79 MPa
       - At 1.5mm depth (remaining 1.5mm):
           σ_pocket = 4.79 × (3/1.5)² = 4.79 × 4.0 = 19.2 MPa  (76.6% of 25 MPa ✓)

  FEA prediction: max(14.3, 19.2) = 19.2 MPa → 76.6% of allowable.
  Min wall in pocket = 1.5mm > 1.2mm spec minimum ✓

Mass estimate (from deep-pocket 29.15g):
  Web height reduction (h_root 90→84, h_tip 15→12):
    Old web avg h: (87+12)/2 = 49.5mm
    New web avg h: (81+9)/2  = 45.0mm
    Δweb = 104 × 2 × (49.5−45.0) = 936 mm³ → 1.16 g
  Extra pocket depth (1.5 vs 1.2mm, 0.3mm more):
    Extra vol = (14.75+24.75) × 49.5 × 0.3 = 39.5 × 49.5 × 0.3 = 587 mm³ → 0.73 g

  Estimated mass: 29.15 − 1.16 − 0.73 = 27.26 g
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for a slim-beam wall bracket."""
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
    margin = bolt_r + 1.5             # 4.75 mm

    plate_t  = 3.0
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    arm_len  = lp[0] + 4.0            # 104 mm (4 mm past load point)

    web_w    = 2.0
    flange_w = 6.0
    flange_t = 1.5
    h_root   = 84.0                   # reduced from 90mm (saves ~0.75g from web)
    h_tip    = 12.0                   # reduced from 15mm (saves ~0.41g from web)
    y_center = lp[1]                  # 25 mm

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

    # ── Wall-face pockets: 1.5mm deep (remaining 1.5mm > 1.2mm min-wall) ─────
    # Back-calc from deep-pocket (1.2mm, 13.3 MPa): σ_unpocketed = 4.79 MPa
    # At 1.5mm: σ = 4.79 × (3/1.5)² = 19.2 MPa < 25.0 MPa ✓ (76.6% of allowable)
    pocket_depth = 1.5

    bolt_clear = bolt_r + 2.0         # 5.25 mm from bolt center
    arm_buf    = 2.0                  # buffer past arm flange edge

    arm_y_min = y_center - flange_w / 2   # 22.0 mm
    arm_y_max = y_center + flange_w / 2   # 28.0 mm

    pkt_z0 = min(bz_coords) + bolt_clear  # 5.25 mm
    pkt_z1 = max(bz_coords) - bolt_clear  # 54.75 mm

    # Left pocket: between left bolt column and arm left edge
    lpkt_y0 = min(by_coords) + bolt_clear  # 5.25 mm
    lpkt_y1 = arm_y_min - arm_buf          # 20.0 mm
    if lpkt_y1 > lpkt_y0 + 2.0 and pkt_z1 > pkt_z0 + 2.0:
        left_pocket = BRepPrimAPI_MakeBox(
            gp_Pnt(0.0, lpkt_y0, pkt_z0),
            gp_Pnt(pocket_depth, lpkt_y1, pkt_z1),
        ).Shape()
        cut_op = BRepAlgoAPI_Cut(shape, left_pocket)
        cut_op.Build()
        shape = cut_op.Shape()

    # Right pocket: between arm right edge and right bolt column
    rpkt_y0 = arm_y_max + arm_buf          # 30.0 mm
    rpkt_y1 = max(by_coords) - bolt_clear  # 54.75 mm
    if rpkt_y1 > rpkt_y0 + 2.0 and pkt_z1 > pkt_z0 + 2.0:
        right_pocket = BRepPrimAPI_MakeBox(
            gp_Pnt(0.0, rpkt_y0, pkt_z0),
            gp_Pnt(pocket_depth, rpkt_y1, pkt_z1),
        ).Shape()
        cut_op = BRepAlgoAPI_Cut(shape, right_pocket)
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
