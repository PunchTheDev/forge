"""
Al-bracket v5: aggressive mass reduction targeting ~39.9g (spec-002).

Baseline: al-bracket v4 (PR #60) passed at 41.81g, 24.7 MPa (22.4% of 110.4 MPa allowable).
Stress headroom: 77.6% → significant further reduction possible.

Changes from al-bracket v4:
  h_root     : 34mm → 31mm   (saves ~0.67g web; arm within plate ✓; load nodes ✓)
  bolt_clear : 6.25mm → 5.05mm (=bolt_r+min_wall; larger pockets: saves ~0.75g)
  arm_buf    : 2.0mm → 1.0mm  (pockets closer to arm: saves ~0.19g)

Unchanged from v4:
  plate_t=2.0mm, pocket_depth=1.2mm, flange_t=0.8mm, flange_w=8mm, h_tip=30mm,
  web_w=2mm, margin=5.05mm

Load node check (h_root=31mm, h_tip=30mm):
  h(x=120) = 31 - (31-30) × 120/124 = 31 - 0.97 = 30.03mm
  |30.03 - 45| = 14.97mm < 15mm tol ✓ (margin: 0.03mm above tol — passes strict inequality)

Arm within plate:
  plate_z1 = max(bz)+margin = 40+5.05 = 45.05mm; h_root=31 < 45.05mm ✓

Bolt ring (margin=5.05mm): clearance = 5.05-4.25 = 0.80mm = spec min_wall ✓
Pocket-to-bolt (bolt_clear=5.05mm): clearance = 5.05-4.25 = 0.80mm = spec min_wall ✓

Stress estimate:
  v4 I = 9,204 mm⁴, c=17mm, FEA=24.7 MPa
  v5 I (h_root=31, flange_t=0.8, flange_w=8, web_h=29.4mm):
    I = 2×8×0.8×(15.5-0.4)² + 2×29.4³/12 = 2918 + 4222 = 7,140 mm⁴, c=15.5mm
  Ratio = (9,204/7,140) × (17/15.5) = 1.289 × 1.097 = 1.414
  Estimated FEA stress = 24.7 × 1.414 = 34.9 MPa vs 110.4 MPa ✓ (31.6%)

Convergence trigger: 77.3 MPa → 34.9 MPa well below → no convergence check expected.

Mass estimate (savings over v4):
  h_root 34→31mm: web_avg_h 30.4→29.4mm → 124×2×1.0=248mm³ → 0.67g
  bolt_clear 6.25→5.05mm: extra pocket area = (37.75+16.75→38.95+18.95mm) × 27.5→29.9mm
    Old: 1,499mm² × 1.2=1,799mm³; New: 1,731mm² × 1.2=2,077mm³ → 278mm³ → 0.75g
  arm_buf 2→1mm: extra 2×1×29.9=59.8mm² × 1.2=71.8mm³ → 0.19g
  Total savings: 0.67+0.75+0.19 = 1.61g → target: 41.81-1.61 = 40.20g
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for al-bracket v5 (aggressive reduction targeting ~40g)."""
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
    margin = bolt_r + min_wall                  # 5.05mm (same as v4)

    plate_t  = 2.0
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin          # 45.05mm

    arm_len  = lp[0] + 4.0                     # 124mm

    web_w    = 2.0
    flange_w = 8.0
    flange_t = 0.8                              # = spec min_wall
    h_root   = 31.0   # arm within plate: 31 < 45.05mm ✓; h(120)=30.03mm, gap=14.97mm < 15mm ✓
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

    # ── Wall-face pockets: 1.2mm deep, tightest valid margins ────────────────
    pocket_depth = 1.2
    bolt_clear = bolt_r + min_wall     # 5.05mm: min valid pocket-to-bolt clearance
    arm_buf    = 1.0                   # 1mm clearance from arm flange

    arm_y_min = y_center - flange_w / 2   # 46.0mm
    arm_y_max = y_center + flange_w / 2   # 54.0mm

    pkt_z0 = min(bz_coords) + bolt_clear
    pkt_z1 = max(bz_coords) - bolt_clear

    # Left pocket
    lpkt_y0 = min(by_coords) + bolt_clear
    lpkt_y1 = arm_y_min - arm_buf
    if lpkt_y1 > lpkt_y0 + 1.0 and pkt_z1 > pkt_z0 + 1.0:
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
    if rpkt_y1 > rpkt_y0 + 1.0 and pkt_z1 > pkt_z0 + 1.0:
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
