"""
Pocket-plate bracket: lean-arm SOTA with mass-relieving pockets on the wall face.

Key insight: the mounting plate (17.5 g of the 32.64 g lean-arm) has large zones
between the four bolt holes that carry minimal load. Boring rectangular pockets from
the wall-facing side (x=0) into those zones removes ~3.8 g while leaving the bolt-hole
rings fully intact and the arm-facing surface solid.

Pocket placement:
  - x: [0, plate_t/2 = 1.5 mm]  — bored from wall side, 1.5 mm solid remains on arm side
  - y: two zones straddling the I-beam arm (centered at y=25):
      Left  [bolt_r+2 = 5.25, arm_y_min - 1 = 21 mm]
      Right [arm_y_max + 1 = 29, bolt_y_max - bolt_r - 2 = 54.75 mm]
  - z: [bolt_r+2 = 5.25, bolt_z_max - bolt_r - 2 = 54.75 mm]
  All four bolt-hole rings (margin 4.75 mm) remain un-pocketed.

Structural analysis — unchanged from lean-arm (pockets remote from critical paths):

  Bolt-hole bearing stress (top bolts, per lean-arm analysis):
    F_bolt ≈ 341 N (bending + shear resultant)
    Bearing area = 2 × bolt_r × plate_t = 2 × 3.25 × 3 = 19.5 mm²
    σ_bearing ≈ 341 / 19.5 = 17.5 MPa < 25.0 MPa allowable ✓
    (pockets do not touch the bolt-hole rings → bearing stress unchanged)

  Arm-root bending stress (unchanged from lean-arm):
    σ_root = M × c / I = 39,240 × 45 / 144,993 = 12.18 MPa ✓

Mass estimate (PLA, 1.24 g/cm³):

  From lean-arm: 32.64 g (FEA-verified)

  Pocket removal:
    Left pocket:  (21 - 5.25) × (54.75 - 5.25) × 1.5 = 15.75 × 49.5 × 1.5 = 1 170 mm³ → 1.45 g
    Right pocket: (54.75 - 29) × (54.75 - 5.25) × 1.5 = 25.75 × 49.5 × 1.5 = 1 912 mm³ → 2.37 g
    Total pocket:                                                                = 3 082 mm³ → 3.82 g

  Shorter arm (104 mm vs 108 mm, 4 mm past load point):
    Web + flange reduction ≈ (4/108) × (10 692 + 1 944) = 468 mm³ → 0.58 g

  Estimated mass: 32.64 - 3.82 - 0.58 ≈ 28.24 g
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for a pocket-plate wall bracket."""
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
    margin = bolt_r + 1.5             # 4.75 mm — minimum structural ring around each bolt hole

    # Mounting plate: 3 mm thick (proven minimum for bolt-hole FEA stress).
    plate_t  = 3.0
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    # Arm: 4 mm past load point (vs 8 mm in lean-arm). Still well inside build volume.
    arm_len = lp[0] + 4.0             # 104 mm

    # I-beam geometry — identical to lean-arm (proven mesh-convergent).
    web_w    = 2.0
    flange_w = 6.0
    flange_t = 1.5

    h_root = 90.0                     # section height at wall (x=0)
    h_tip  = 15.0                     # section height at tip  (x=arm_len)

    y_center = lp[1]                  # 25 mm

    # ── Arm (I-beam) ──────────────────────────────────────────────────────────
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

    # ── Wall-face pockets ─────────────────────────────────────────────────────
    # Pocket clearances:
    #   From bolt holes:  bolt_r + 2.0 mm  (2 mm past hole wall)
    #   From arm flanges: 1.0 mm gap
    pocket_depth = plate_t / 2.0      # 1.5 mm — leaves 1.5 mm solid on arm side
    pclear_bolt  = bolt_r + 2.0       # 5.25 mm from bolt center
    pclear_arm   = 1.0                # gap from arm flange edge

    arm_y_min = y_center - flange_w / 2  # 22.0 mm
    arm_y_max = y_center + flange_w / 2  # 28.0 mm

    pkt_z0 = min(bz_coords) + pclear_bolt  # 5.25 mm
    pkt_z1 = max(bz_coords) - pclear_bolt  # 54.75 mm

    # Left pocket: between left bolt column and arm left edge
    lpkt_y0 = min(by_coords) + pclear_bolt   # 5.25 mm
    lpkt_y1 = arm_y_min - pclear_arm         # 21.0 mm
    if lpkt_y1 > lpkt_y0 + 2.0 and pkt_z1 > pkt_z0 + 2.0:
        left_pocket = BRepPrimAPI_MakeBox(
            gp_Pnt(0.0, lpkt_y0, pkt_z0),
            gp_Pnt(pocket_depth, lpkt_y1, pkt_z1),
        ).Shape()
        cut_op = BRepAlgoAPI_Cut(shape, left_pocket)
        cut_op.Build()
        shape = cut_op.Shape()

    # Right pocket: between arm right edge and right bolt column
    rpkt_y0 = arm_y_max + pclear_arm         # 29.0 mm
    rpkt_y1 = max(by_coords) - pclear_bolt   # 54.75 mm
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
