"""
Al-bracket v2: thinner plate + thinner flanges targeting ~49g (spec-002).

Baseline: al-bracket v3 (PR #48) passed at 65.41g, 26.1 MPa (23.6% of 110.4 MPa allowable).
Stress headroom: 76.4% → room to reduce cross-sections significantly.

Changes from al-bracket v3:
  plate_t  : 3.0mm → 2.0mm  (net plate saving: ~9.4g)
  pocket_depth: 1.8mm → 1.2mm  (forced: plate_t - min_wall = 2.0 - 0.8 = 1.2mm max)
  flange_t : 2.5mm → 1.5mm  (arm flanges thinner; saves ~6.7g)
  h_tip    : 31mm  → 30mm   (minimum to keep load nodes within 15mm tol of z=45mm)

Unchanged from v3:
  flange_w = 10mm (clearance from bolt at y=40: arm_edge=45mm, hole_edge=44.25mm → 0.75mm ✓)
  h_root   = 43mm (arm fully within plate_z1=45.75mm → no junction stress ✓)
  web_w    = 2mm
  arm_len  = 124mm (lp[0]=120 + 4mm)

Load node check (h_tip=30mm):
  h(x=120) = 43 - (43-30) × 120/124 = 43 - 12.58 = 30.4mm
  |30.4 - 45| = 14.6mm < tol=15mm ✓

Stress estimate (I-section ratio):
  Old I (flange_t=2.5, flange_w=10, h_root=43): 29,650 mm⁴
  New I (flange_t=1.5, flange_w=10, h_root=43):
    web_h_root = 43 - 2×1.5 = 40mm
    I = 2×10×1.5×(21.5-0.75)² + 2×40³/12 = 12,919 + 10,667 = 23,586 mm⁴
  Ratio = 29,650 / 23,586 = 1.26
  Estimated FEA stress = 26.1 × 1.26 = 32.9 MPa vs 110.4 MPa ✓ (29.8% of allowable)

Wall check:
  plate_t - pocket_depth = 2.0 - 1.2 = 0.8mm = spec min_wall ✓
  flange_t = 1.5mm > 0.8mm min_wall ✓

Mass estimate (ρ_Al = 2.7e-3 g/mm³):
  Plate: 2.0 × 91.5 × 51.5 = 9,431 mm³
    - 6 bolt holes: 6 × π × 4.25² × 2.0 = 681 mm³
    - Pockets (1.2mm):
        Left (y:6.25→43, z:6.25→33.75): 1.2 × 36.75 × 27.5 = 1,213 mm³
        Right (y:57→73.75, z:6.25→33.75): 1.2 × 16.75 × 27.5 = 553 mm³
    Net plate: 9431 - 681 - 1766 = 6,984 mm³ → 18.9g
  Web: avg_h = (40+27)/2=33.5mm → 124×2×33.5 = 8,308 mm³ → 22.4g
  Flanges: 2 × 124 × 10 × 1.5 = 3,720 mm³ → 10.0g
  Total (less arm-plate overlap): ~49g
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for al-bracket v2 (thinner plate + flanges)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d = c["bolt_diameter_clearance_mm"]   # 8.5mm → bolt_r=4.25mm
    lp = c["load_point_mm"]                    # [120, 50, 45]

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    bolt_r = bolt_d / 2.0
    margin = bolt_r + 1.5                       # 5.75mm structural ring

    plate_t  = 2.0                              # reduced from 3.0mm
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin          # 45.75mm

    arm_len  = lp[0] + 4.0                     # 124mm

    web_w    = 2.0
    flange_w = 10.0   # 10mm: arm edge at y=45mm, 0.75mm clear of bolt at y=40 (hole r=4.25)
    flange_t = 1.5                              # reduced from 2.5mm (min_wall check: 1.5>0.8 ✓)
    h_root   = 43.0   # arm fully within plate: top at z=43mm < plate_z1=45.75mm → no junction
    h_tip    = 30.0   # arm top at x=120mm = 30.4mm; gap to load z=45mm = 14.6mm < 15mm tol ✓
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

    # ── Wall-face pockets: 1.2mm deep (0.8mm remaining = spec min_wall) ──────
    # plate_t=2.0mm, min_wall=0.8mm → max pocket_depth = 1.2mm
    pocket_depth = 1.2

    bolt_clear = bolt_r + 2.0         # 6.25mm
    arm_buf    = 2.0

    arm_y_min = y_center - flange_w / 2   # 45.0mm
    arm_y_max = y_center + flange_w / 2   # 55.0mm

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
