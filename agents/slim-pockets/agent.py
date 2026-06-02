"""
Slim-pockets bracket: mid-arm with deeper pockets + narrower flanges.

Lesson from nano-arm (PR #46): h_root=68mm (1.75mm gap above plate) fails mesh
convergence (deviation=76.8%). Safe minimum is h_root=70mm (3.75mm gap, proven by
mid-arm PR #44). This design keeps h_root=70mm and layers two other savings:

Changes from mid-arm (26.57g, 14.7 MPa):
  pocket_depth 1.2mm → 1.5mm  (remaining plate wall 1.5mm > 1.2mm min_wall ✓)
  flange_w     6mm   → 5mm    (wider-than-thick flange; mesh-stable at aspect ratio 5/1.5=3.3)

Clearance (unchanged): arm top flange z=[68.5,70mm], plate top z=64.75mm → 3.75mm ✓
Taper ratio (unchanged): 70/15 = 4.67:1 < 6:1 limit ✓

Section modulus (arm root, h_root=70mm, flange_w=5mm):
  c         = h_root / 2 = 35mm
  I_web     = 2 × (67)³/12 = 50,131 mm⁴   (67 = h_root − 2×flange_t)
  I_flange  = 2 × 5 × 1.5 × (35 − 0.75)² = 17,574 mm⁴
  I_total   = 67,705 mm⁴
  Z         = I/c = 1,934 mm³
  σ_predict = M/Z = 39,240/1,934 = 20.3 MPa  (81.1% of allowable)
  FEA overestimates ~1.3×  → actual ≈ 15.6 MPa (62% of allowable ✓)

Mass estimate (from mid-arm 26.57g):
  Δpocket_depth (1.5 vs 1.2mm):
    Left:  0.3 × 14.75 × 49.5 = 219 mm³
    Right: 0.3 × 24.25 × 49.5 = 360 mm³   (right pocket gains 0.5mm from flange_w=5 vs 6)
    Total: 579 mm³ → 0.72g
  Δflange_w (5 vs 6mm): 2 × 104 × 1.5 × 1 = 312 mm³ → 0.39g
  Total saving: 1.11g
  Target: 26.57 − 1.11 = 25.46g
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for a slim-pockets wall bracket."""
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
    margin = bolt_r + 1.5             # structural ring around each bolt hole

    plate_t  = 3.0
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin  # 64.75mm

    arm_len  = lp[0] + 4.0            # 104mm (4mm past load point)

    web_w    = 2.0
    flange_w = 5.0                    # reduced 6→5mm; saves arm flange mass
    flange_t = 1.5
    h_root   = 70.0                   # MUST stay at 70mm: proven safe by mid-arm (PR #44)
                                      # h_root=68mm (1.75mm gap) fails mesh convergence
    h_tip    = 15.0                   # floor: shorter causes mesh instability
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

    # ── Wall-face pockets: 1.5mm deep (1.5mm remaining > 1.2mm min-wall) ─────
    pocket_depth = 1.5

    bolt_clear = bolt_r + 2.0         # buffer past bolt hole wall
    arm_buf    = 2.0                  # buffer past arm flange edge

    arm_y_min = y_center - flange_w / 2   # 22.5mm
    arm_y_max = y_center + flange_w / 2   # 27.5mm

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
