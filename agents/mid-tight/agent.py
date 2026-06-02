"""
Mid-tight: slim-arm-18 with tighter margins, bisecting tight-arm failure (spec-001).

Baseline: slim-arm-18 (24.81g, 13.7 MPa). tight-arm failed at 33.1 MPa > 25.0 MPa.

Diagnosis: tight-arm used bolt_clear=4.45mm (bridge=1.2mm) + pocket_depth=1.8mm.
The 1.2mm×1.2mm pocket-bolt corner (pocket_depth=1.8mm, remaining_wall=1.2mm, bridge=1.2mm)
creates extreme notch stress concentration → 2.4× stress jump.

Fix: keep bolt_clear=4.75mm (bridge=1.5mm); all other tight-arm changes retained.

Changes from slim-arm-18 (24.81g, 13.7 MPa):
  margin    = bolt_r + min_wall = 4.45mm (from bolt_r + 1.5 = 4.75mm)
              → trims plate edges; saves ~0.31g
  bolt_clear = bolt_r + 1.5 = 4.75mm (from bolt_r + 2.0 = 5.25mm)
              → wider pockets (1.5mm vs 2.0mm bridge above bolt_r); saves ~0.25g
  arm_len   = lp[0] + 2.0 = 102mm (from lp[0] + 4.0 = 104mm)
              → shorter tip; saves ~0.10g
  arm_buf   = 1.0mm (from 2.0mm)
              → pocket closer to arm flange; saves ~0.18g (combined with bolt_clear)

Total estimated savings: 0.31 + 0.43 + 0.10 = 0.84g → target: 24.81 - 0.84 = 23.97g

Stress estimate (σ ∝ bridge^(-1.73), calibrated from slim-arm-18 and tight-arm data):
  slim-arm-18: bridge=2.0mm → 13.7 MPa
  tight-arm: bridge=1.2mm → 33.1 MPa
  n = ln(33.1/13.7) / ln(2.0/1.2) = 0.882 / 0.511 = 1.73
  Predicted: 13.7 × (2.0/1.5)^1.73 = 13.7 × 1.58 = 21.7 MPa < 25.0 MPa ✓

Convergence check: 21.7 MPa > 17.5 MPa (70% × 25 MPa) → check will trigger.
Plate is 3.0mm (proven floor), pocket geometry is solid — convergence should pass.

Wall checks:
  bolt ring: margin - bolt_r = 4.45 - 3.25 = 1.2mm = min_wall ✓
  pocket-to-bolt bridge: bolt_clear - bolt_r = 4.75 - 3.25 = 1.5mm > min_wall ✓
  pocket remaining wall: plate_t - pocket_depth = 3.0 - 1.8 = 1.2mm = min_wall ✓
  flange_t = 1.2mm = min_wall ✓
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for mid-tight wall bracket (bisecting tight-arm failure)."""
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
    margin = bolt_r + min_wall              # 4.45mm: tightest valid bolt ring

    plate_t  = 3.0                    # proven floor for spec-001
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    arm_len  = lp[0] + 2.0            # 102mm (from 104mm; saves ~0.10g)

    web_w    = 2.0
    flange_w = 6.0
    flange_t = 1.2                    # =min_wall (proven safe in slim-arm-18)
    h_root   = 70.0
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

    # ── Wall-face pockets: 1.8mm deep ─────────────────────────────────────────
    # bolt_clear=4.75mm: bridge above bolt_r = 1.5mm (safe; tight-arm 1.2mm failed)
    pocket_depth = 1.8
    bolt_clear = bolt_r + 1.5          # 4.75mm: 1.5mm bridge (vs 1.2mm in failed tight-arm)
    arm_buf    = 1.0                   # 1mm clearance from arm flange (from 2.0mm)

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
