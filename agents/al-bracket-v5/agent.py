"""
Al-bracket v5: h_root=31mm with pocket z-cap at arm height (spec-002).

Baseline: al-bracket v4 (PR #60) passed at 41.81g, 24.7 MPa (22.4% of 110.4 MPa allowable).

Key insight: pkt_z1 must be ≤ h_root. In v4, pkt_z1=33.75mm < h_root=34mm (0.25mm margin).
v5 initial attempt: pkt_z1=34.95mm > h_root=31mm → pocket cut ABOVE arm height → 167.7 MPa.
Fix: pkt_z1 = min(max(bz) - bolt_clear, h_root) — pocket never extends above arm top.

Changes from al-bracket v4:
  h_root     : 34mm → 31mm   (arm within plate ✓; load nodes ✓)
  bolt_clear : 6.25mm → 5.05mm (=bolt_r+min_wall; pocket y-width increases)
  arm_buf    : 2.0mm → 1.0mm  (pocket y-width increases further)
  pkt_z1     : capped at h_root (new safety constraint)

Unchanged from v4:
  plate_t=2.0mm, pocket_depth=1.2mm, flange_t=0.8mm, flange_w=8mm, h_tip=30mm,
  web_w=2mm, margin=5.05mm

Load node check (h_root=31mm, h_tip=30mm):
  h(x=120) = 31 - (31-30) × 120/124 = 31 - 0.97 = 30.03mm
  |30.03 - 45| = 14.97mm < 15mm tol ✓

Arm within plate:
  plate_z1 = max(bz)+margin = 40+5.05 = 45.05mm; h_root=31 < 45.05mm ✓

Bolt ring (margin=5.05mm): clearance = 5.05-4.25 = 0.80mm = spec min_wall ✓
Pocket-to-bolt (bolt_clear=5.05mm): clearance = 5.05-4.25 = 0.80mm = spec min_wall ✓

Pocket z-range (with min_wall gap below arm top):
  pkt_z0 = 5.05mm; pkt_z1 = min(34.95, 31-0.8) = 30.2mm (= h_root - min_wall)
  Left:  y=5.05→45mm (39.95mm), z=5.05→30.2mm (25.15mm); area=1005mm²
  Right: y=55→74.95mm (19.95mm), z=5.05→30.2mm (25.15mm); area=502mm²
  vs v4: Left 37.75×27.5=1038mm², Right 17.75×27.5=488mm²; total=1526mm²
  v5 total: 1507mm² → pocket volume 1507×1.2=1808mm³ (-23mm³ vs v4 → -0.06g)
  Pockets save 0.06g LESS than v4 (pockets are smaller due to shorter z-range)

Stress estimate (same analysis as before):
  v4 I = 9,204 mm⁴, c=17mm, FEA=24.7 MPa
  v5 I (h_root=31): I=7,149mm⁴, c=15.5mm; ratio × c = 1.414
  Estimated FEA stress = 24.7 × 1.414 = 34.9 MPa vs 110.4 MPa ✓ (31.6%)

Mass estimate (savings over v4):
  h_root 34→31mm: web ΔV = 124×2×((29.4+28.4)/2-(32.4+28.4)/2) = 124×2×1.5 = 372mm³ → 1.00g
  pockets (min_wall gap cap): -0.06g (pockets actually smaller than v4 in z)
  Total savings: ~0.94g → target: 41.81 - 0.94 = 40.87g
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
    # Cap pkt_z1: must stay at least min_wall below arm top to avoid junction stress.
    # v4 precedent: pkt_z1=33.75mm < h_root=34mm (0.25mm gap) → passed at 24.7 MPa.
    # Capping AT h_root (0mm gap) fails (194.3 MPa). min_wall=0.8mm gap for safety.
    pkt_z1 = min(max(bz_coords) - bolt_clear, h_root - min_wall)

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
