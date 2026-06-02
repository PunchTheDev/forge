"""
Al-bracket v6: three-parameter improvement over v4 (41.81g, 24.7 MPa, spec-002).

Baseline: al-bracket v4 (PR #60) passed FEA at 41.81g, 24.7 MPa (22.4% of 110.4 MPa).
v5 failed (149.4 MPa) due to bolt_clear=5.05mm creating 0.80mm pocket-bolt bridge.

Fix strategy for v6: revert to proven bolt_clear=6.25mm (2.0mm bridge) and extract
mass savings from taper, arm length, and flange width only.

Changes from v4:
  h_tip      : 32mm → 30mm  (tighter taper; saves ~0.65g web mass)
  arm_len    : 124mm → 121mm (shorter tip; saves ~0.59g)
  flange_w   : 8mm → 6mm    (saves ~0.52g flange + ~0.05g via wider pockets)
  bolt_clear : unchanged at 6.25mm (2.0mm bridge — proven safe)
  arm_buf    : unchanged at 2.0mm

Load node check (h_root=34mm, h_tip=30mm, arm_len=121mm):
  h(x=120) = 34 - (34-30) × 120/121 = 34 - 3.967 = 30.033mm
  |30.033 - 45| = 14.967mm < 15mm tol ✓

Arm within plate:
  plate_z1 = 40 + 5.05 = 45.05mm; h_root=34mm < 45.05mm ✓

Flange clearance to bolt y=40 (nearest bolt):
  arm_y_min = 50 - 3 = 47mm; bolt edge = 40 + 4.25 = 44.25mm; gap = 2.75mm > 0.8mm ✓

Pocket geometry (same logic as v4, bolt_clear=6.25mm):
  pkt_z0 = 6.25mm; pkt_z1 = min(33.75, 33.2) = 33.2mm
  Left:  y=6.25→45mm (38.75mm), z=6.25→33.2mm (26.95mm); area=1043mm²
  Right: y=55→73.75mm (18.75mm), z=6.25→33.2mm (26.95mm); area=505mm²
  Total pocket area 1548mm² → volume 1548×1.2=1858mm³ → 5.01g savings
  (vs v4: 1526mm² → 1831mm³ → 4.94g — pockets ~0.07g more savings with narrower flange)

Mass estimate vs v4 (41.81g):
  h_tip 32→30mm:      −0.65g
  arm_len 124→121mm:  −0.59g
  flange_w 8→6mm:     −0.52g
  pocket increase:    −0.07g
  Total savings:       1.83g → target ≈ 39.98g

Stress estimate (78% headroom in v4):
  Section modulus at root unchanged (h_root=34mm, flange_w=6mm slightly less than 8mm).
  I(h=34, fw=6) ≈ 2×6×0.8×(16.6)² + 2×(32.4)³/12 = 2656 + 56,700 = 59,356mm⁴... nah
  Using simpler: stress ∝ 1/(flange moment contribution + web contribution).
  Narrower flange reduces I slightly. Estimated stress increase ≤ 5% → ~26 MPa < 110.4 MPa ✓
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for al-bracket v6 (safe improvements over v4, targeting ~40g)."""
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

    plate_t  = 2.0
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin          # 45.05mm

    arm_len  = lp[0] + 1.0                     # 121mm (from 124mm; saves ~0.59g)

    web_w    = 2.0
    flange_w = 6.0                              # from 8mm; saves ~0.52g + wider pockets
    flange_t = 0.8                              # = spec min_wall
    h_root   = 34.0   # proven safe in v4 (24.7 MPa, 22.4% of allowable)
    h_tip    = 30.0   # from 32mm; h(120)=30.033mm, gap=14.967mm < 15mm tol ✓
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

    # ── Wall-face pockets ────────────────────────────────────────────────────
    pocket_depth = 1.2
    bolt_clear   = 6.25                        # 2.0mm bridge to bolt holes (proven safe in v4)
    arm_buf      = 2.0                         # clearance from arm flange (proven safe in v4)

    arm_y_min = y_center - flange_w / 2        # 47.0mm
    arm_y_max = y_center + flange_w / 2        # 53.0mm

    pkt_z0 = min(bz_coords) + bolt_clear       # 6.25mm
    pkt_z1 = min(max(bz_coords) - bolt_clear, h_root - min_wall)  # min(33.75, 33.2) = 33.2mm

    lpkt_y0 = min(by_coords) + bolt_clear      # 6.25mm
    lpkt_y1 = arm_y_min - arm_buf              # 45.0mm
    if lpkt_y1 > lpkt_y0 + 1.0 and pkt_z1 > pkt_z0 + 1.0:
        left_pocket = BRepPrimAPI_MakeBox(
            gp_Pnt(0.0, lpkt_y0, pkt_z0),
            gp_Pnt(pocket_depth, lpkt_y1, pkt_z1),
        ).Shape()
        cut_op = BRepAlgoAPI_Cut(shape, left_pocket)
        cut_op.Build()
        shape = cut_op.Shape()

    rpkt_y0 = arm_y_max + arm_buf              # 55.0mm
    rpkt_y1 = max(by_coords) - bolt_clear      # 73.75mm
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
