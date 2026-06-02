"""
Deep-pocket bracket: pocket-plate with 1.2mm pocket depth targeting ~29.1g.

Back-calculation from pocket-plate v2 (30.12g, 12.6 MPa FEA):
  σ_pocketed = σ_unpocketed × (plate_t / remaining)²
  With 0.8mm pockets (remaining=2.2mm):  σ_total = 12.6 MPa
  Solving: σ_unpocketed_at_pocket = 12.6 / (3/2.2)² = 12.6 / 1.857 = 6.78 MPa

  At 1.2mm depth (remaining=1.8mm):
    σ_pocketed = 6.78 × (3/1.8)² = 6.78 × 2.778 = 18.8 MPa < 25.0 MPa ✓  (25% headroom)

  Pocket-edge Kt at 2mm arm buffer ≈ 1.0 (verified by v2 result).

Mass estimate (PLA, 1.24 g/cm³):
  From pocket-plate (30.12 g FEA-verified):
  Extra pocket depth vs v2: 39.5 × 49.5 × (1.2 − 0.8) = 39.5 × 49.5 × 0.4 = 782 mm³ → 0.97 g
  Estimated mass: 30.12 − 0.97 ≈ 29.15 g
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for a deep-pocket wall bracket."""
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

    plate_t  = 3.0
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    arm_len  = lp[0] + 4.0            # 104 mm

    web_w    = 2.0
    flange_w = 6.0
    flange_t = 1.5
    h_root   = 90.0
    h_tip    = 15.0
    y_center = lp[1]

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

    # ── Plate ─────────────────────────────────────────────────────────────────
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

    # ── Wall-face pockets: 1.2mm deep (remaining 1.8mm > 1.2mm min-wall) ─────
    pocket_depth = 1.2
    bolt_clear   = bolt_r + 2.0           # 5.25 mm
    arm_buf      = 2.0                    # buffer past arm flange edge

    arm_y_min = y_center - flange_w / 2   # 22.0 mm
    arm_y_max = y_center + flange_w / 2   # 28.0 mm

    pkt_z0 = min(bz_coords) + bolt_clear  # 5.25 mm
    pkt_z1 = max(bz_coords) - bolt_clear  # 54.75 mm

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
