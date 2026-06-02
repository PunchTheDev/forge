"""
Al-bracket v3: aggressive arm reduction targeting ~45g (spec-002).

Baseline: al-bracket v2 (PR #53) passed at 50.72g, 20.4 MPa (18.5% of 110.4 MPa allowable).
Stress headroom: 81.5% → room for much thinner arm cross-sections.

Changes from al-bracket v2:
  flange_t : 1.5mm → 1.0mm  (saves ~3.35g; > 0.8mm min_wall ✓)
  flange_w : 10mm  → 8mm    (saves ~1.34g; bolt clearance: arm_y_min=46mm > hole_edge=44.25mm ✓)
  h_root   : 43mm  → 38mm   (arm fully within plate_z1=45.75mm ✓; saves ~1.0g from web)

Unchanged from v2:
  plate_t    = 2.0mm (confirmed safe by v2)
  pocket_depth = 1.2mm (forced by min_wall=0.8mm)
  h_tip      = 30mm (load node check: h(120)=30.3mm, gap=14.7mm < 15mm ✓)
  web_w      = 2mm

Bolt clearance check (flange_w=8mm):
  arm_y_min = 50 - 4 = 46mm; bolt hole edge at y=40+4.25=44.25mm → clearance=1.75mm ✓

Load node check (h_root=38mm, h_tip=30mm):
  h(x=120) = 38 - (38-30) × 120/124 = 38 - 7.74 = 30.26mm
  |30.26 - 45| = 14.74mm < tol=15mm ✓

Stress estimate (I-section change from v2):
  v2 I (flange_t=1.5, flange_w=10, h_root=43): 23,586 mm⁴, c=21.5mm
  v3 I (flange_t=1.0, flange_w=8, h_root=38):
    web_h = 38 - 2×1.0 = 36mm
    I = 2×8×1.0×(19-0.5)² + 2×36³/12 = 5,477 + 7,776 = 13,253 mm⁴, c=19mm
  Ratio = (23,586/13,253) × (21.5/19) = 1.78 × 1.13 = 2.01
  Estimated FEA stress = 20.4 × 2.01 = 41.0 MPa vs 110.4 MPa ✓ (37.1% of allowable)

Convergence trigger: 70% × 110.4 = 77.3 MPa. 41.0 MPa is well below → no convergence check.

Wall checks:
  plate_t - pocket_depth = 2.0 - 1.2 = 0.8mm = spec min_wall ✓
  flange_t = 1.0mm > 0.8mm min_wall ✓

Mass estimate (ρ_Al = 2.7e-3 g/mm³):
  Plate (same as v2): 6,984 mm³ → 18.9g
  Web: avg_h = (36+28)/2=32mm → 124×2×32 = 7,936 mm³ → 21.4g
  Flanges: 2 × 124 × 8 × 1.0 = 1,984 mm³ → 5.4g
  Less arm-plate overlap: ~690 mm³ → -1.9g
  Total: ~43.8g
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for al-bracket v3 (aggressive arm reduction)."""
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

    plate_t  = 2.0                              # confirmed safe (v2 passed)
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin          # 45.75mm

    arm_len  = lp[0] + 4.0                     # 124mm

    web_w    = 2.0
    flange_w = 8.0    # reduced from 10mm: arm_y_min=46mm, hole edge=44.25mm → 1.75mm clearance ✓
    flange_t = 1.0                              # reduced from 1.5mm (still > 0.8mm min_wall ✓)
    h_root   = 38.0   # arm within plate: 38 < 45.75mm ✓; web_h=36mm
    h_tip    = 30.0   # h(120mm)=30.26mm; gap to z=45 = 14.74mm < 15mm tol ✓
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
    pocket_depth = 1.2

    bolt_clear = bolt_r + 2.0         # 6.25mm
    arm_buf    = 2.0

    arm_y_min = y_center - flange_w / 2   # 46.0mm
    arm_y_max = y_center + flange_w / 2   # 54.0mm

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
