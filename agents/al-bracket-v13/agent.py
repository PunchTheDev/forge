"""
Al-bracket v13: plate_t=1.5mm + flange_w=5mm vs v10 (35.846g, 50.37 MPa).

Baseline: al-bracket v10 (PR #76): plate_t=1.5mm, h_root=32mm, fw=6mm. 35.846g, 50.37 MPa.

Failures so far:
  v8 (plate_t=2.0, h_root=31mm, fw=5mm): 188.6 MPa — fw=5mm + h_root=31mm = bad combo.
  v12 (plate_t=1.2mm, h_root=32mm, fw=6mm): 203.9 MPa — plate_t < 1.5mm fails.

Key insight: v8's 188 MPa was due to fw=5mm + h_root=31mm together. At h_root=32mm
  (larger arm section), fw=5mm should behave proportionally.

Strategy: reduce flange_w from 6mm to 5mm, keep plate_t=1.5mm + h_root=32mm.
  fw change affects arm section modulus only. The plate stress is unchanged.

Load node check (unchanged from v10): h_root=32mm, h(120)=30.017mm < 45mm ✓

Mass estimate vs v10 (35.846g):
  Both flanges: 2 × arm_len × Δfw × flange_t = 2 × 121 × 1 × 0.8 = 193.6mm³ × 2.7e-3 = 0.523g
  Target: 35.846 - 0.52 = ~35.33g

Stress estimate (arm section only, plate unchanged):
  I_flange ∝ flange_w; ΔI_total for fw 6→5mm:
  I_flanges(6mm) = 2×6×0.8×(16-0.4)² ≈ 2×4.8×243.4 = 2336mm⁴ (rough)
  I_flanges(5mm) = 2×5×0.8×15.6² ≈ 1947mm⁴
  ΔI ≈ 389mm⁴ out of large total. Small relative change → modest stress increase.
  Conservative estimate: 50.37 × 1.2 = ~60 MPa < 110.4 MPa ✓

plate_t=1.5mm, h_root=32mm, h_tip=30mm, all else from v10.
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for al-bracket v13 (plate_t=1.5mm + fw=5mm, targeting ~35.33g)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d = c["bolt_diameter_clearance_mm"]   # 8.5mm → bolt_r=4.25mm
    lp = c["load_point_mm"]                    # [120, 50, 45]
    min_wall = c.get("min_wall_thickness_mm", 0.8)

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    bolt_r = bolt_d / 2.0
    margin = bolt_r + min_wall                  # 5.05mm

    plate_t  = 1.5   # proven floor from v10
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin          # 45.05mm

    arm_len  = lp[0] + 1.0                     # 121mm

    web_w    = 2.0
    flange_w = 5.0   # from 6mm; saves 0.52g in arm flanges
    flange_t = 0.8                              # = min_wall
    h_root   = 32.0   # h(120)=30.017mm, |30.017-45|=14.983mm < 15 ✓
    h_tip    = 30.0
    y_center = lp[1]  # 50mm

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

    # ── Wall-face pockets: 1.2mm deep (plate_t=2.0, min_wall=0.8) ────────────
    pocket_depth = plate_t - min_wall           # 1.2mm
    bolt_clear   = bolt_r + 2.0 * min_wall     # 6.25mm: 2×min_wall bridge (proven safe in v4)
    arm_buf      = 2.0                          # clearance from arm flange

    arm_y_min = y_center - flange_w / 2        # 47mm
    arm_y_max = y_center + flange_w / 2        # 53mm

    pkt_z0 = min(bz_coords) + bolt_clear
    pkt_z1 = max(bz_coords) - bolt_clear

    # Left pocket (between left plate edge and arm)
    lpkt_y0 = min(by_coords) + bolt_clear
    lpkt_y1 = arm_y_min - arm_buf
    if lpkt_y1 > lpkt_y0 + 2.0 and pkt_z1 > pkt_z0 + 2.0:
        left_pocket = BRepPrimAPI_MakeBox(
            gp_Pnt(0.0, lpkt_y0, pkt_z0),
            gp_Pnt(pocket_depth, lpkt_y1, pkt_z1),
        ).Shape()
        cut_op = BRepAlgoAPI_Cut(shape, left_pocket)
        cut_op.Build()
        shape = cut_op.Shape()

    # Right pocket (between arm and right plate edge)
    rpkt_y0 = arm_y_max + arm_buf
    rpkt_y1 = max(by_coords) - bolt_clear
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
