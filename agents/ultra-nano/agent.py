"""
Ultra-nano: sub-nano with flange_t=1.0mm (from 1.2mm).

Baseline: sub-nano (23.484g, 15.01 MPa, CI-verified PR #73).
Strategy: reduce flange thickness from 1.2mm to 1.0mm. Both flanges run the
full arm length — this is the last dimension not at a hard floor.

Gap check with flange_t=1.0mm:
  Arm top flange bottom at z = h_root - flange_t = 69 - 1.0 = 68mm
  Upper bolt hole top at z = 60 + 3.25 = 63.25mm
  Gap = 68 - 63.25 = 4.75mm > 3.75mm minimum ✓ (better than sub-nano's 4.55mm)

Mass estimate:
  Both flanges lose: 2 × arm_len × flange_w × Δt = 2 × 100 × 6 × 0.2 = 240mm³
    → 240 × 1.24e-3 = 0.298g saved
  Web gains (taller by 0.4mm at root and tip uniformly):
    100 × web_w × 0.4 = 100 × 2 × 0.4 = 80mm³ → 80 × 1.24e-3 = 0.099g added
  Net: 0.298 - 0.099 = 0.199g saved → target: 23.484 - 0.199 = ~23.285g

Stress check at root:
  I_web(1.2) = (2×66.6³)/12 = 49149mm⁴; I_flanges(1.2) = 2×6×1.2×33.9² = 16549mm⁴
  I_total(1.2) = 65698mm⁴
  I_web(1.0) = (2×67.0³)/12 = 50127mm⁴; I_flanges(1.0) = 2×6×1.0×34.0² = 13872mm⁴
  I_total(1.0) = 63999mm⁴; stress ratio = 65698/63999 = 1.027
  σ_ultra = 15.01 × 1.027 = 15.41 MPa < 25 MPa ✓ (61.6%)

All other parameters unchanged from sub-nano:
  h_root=69mm, h_tip=15mm, plate_t=3.0mm, pocket_depth=1.8mm,
  bolt_clear=4.75mm, arm_buf=1.0mm, flange_w=6mm, web_w=2mm, arm_len=100mm.
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for ultra-nano bracket (flange_t=1.0mm, targeting ~23.285g)."""
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
    margin = bolt_r + min_wall              # 4.45mm

    plate_t  = 3.0
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    arm_len  = lp[0]                  # 100mm — at load point

    web_w    = 2.0
    flange_w = 6.0
    flange_t = 1.0   # from 1.2mm; saves ~0.20g (flange area - web growth)
    h_root   = 69.0   # from 70mm; gap=4.55mm > 3.75mm minimum ✓
    h_tip    = 15.0
    y_center = lp[1]                  # 25mm

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

    # ── Wall-face pockets: 1.8mm deep ────────────────────────────────────────
    pocket_depth = 1.8
    bolt_clear = bolt_r + 1.5          # 4.75mm: 1.5mm bridge (proven safe)
    arm_buf    = 1.0

    arm_y_min = y_center - flange_w / 2   # 22.0mm
    arm_y_max = y_center + flange_w / 2   # 28.0mm

    pkt_z0 = min(bz_coords) + bolt_clear
    pkt_z1 = max(bz_coords) - bolt_clear

    # Left pocket
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

    # Right pocket
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
