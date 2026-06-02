"""
Pocket-plate bracket v2: shallow pockets on wall face — lean-arm with ~2.5g lighter plate.

Lesson from v1 (PR #34): 1.5 mm pockets failed FEA at 36.2 MPa.
Root cause: plate bending stress in transfer zone ≈ 9 MPa (unpocketed).
With 1.5 mm remaining thickness: σ × (3/1.5)² = 9 × 4.0 = 36 MPa — matches FEA.

v2 fix: reduce pocket depth to 0.8 mm (leaves 2.2 mm solid on arm side).
  σ_pocketed = 9 × (3/2.2)² = 9 × 1.86 = 16.7 MPa < 25 MPa allowable ✓
  With Kt ≈ 1.3 for pocket edge: 1.3 × 16.7 = 21.7 MPa < 25 MPa ✓
Also widens arm-buffer from 1 mm to 2 mm (pocket edges 2 mm from arm flanges).

Pocket placement (from wall face x=0, depth 0.8 mm):
  Left  pocket: y [5.25, 20.0], z [5.25, 54.75]  (between left bolt column and arm left edge − 2 mm)
  Right pocket: y [30.0, 54.75], z [5.25, 54.75]  (between arm right edge + 2 mm and right bolt column)
  All bolt-hole rings (margin 4.75 mm from centre) remain solid.

Mass estimate (PLA, 1.24 g/cm³):

  From lean-arm: 32.64 g (FEA-verified)

  Left pocket:  (20.0 − 5.25) × (54.75 − 5.25) × 0.8 = 14.75 × 49.5 × 0.8 = 584 mm³ → 0.72 g
  Right pocket: (54.75 − 30.0) × (54.75 − 5.25) × 0.8 = 24.75 × 49.5 × 0.8 = 980 mm³ → 1.21 g
  Arm 104 mm (vs 108 mm, still 4 mm past load point):
    (4/108) × (10 296 + 1 944) = (4/108) × 12 240 = 453 mm³ → 0.56 g

  Estimated mass: 32.64 − 0.72 − 1.21 − 0.56 ≈ 30.15 g
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

    plate_t  = 3.0
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    arm_len = lp[0] + 4.0             # 104 mm (4 mm past load point)

    web_w    = 2.0
    flange_w = 6.0
    flange_t = 1.5
    h_root   = 90.0
    h_tip    = 15.0
    y_center = lp[1]                  # 25 mm

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

    # ── Wall-face pockets (v2: shallower, wider arm buffer) ───────────────────
    # Depth: 0.8 mm → leaves 2.2 mm solid on arm side.
    # Plate bending stress in pocket zone ≈ 9 × (3/2.2)² = 16.7 MPa < 25 MPa ✓
    # Edge Kt ≈ 1.3 → 21.7 MPa < 25 MPa ✓
    pocket_depth = 0.8

    # Clearances
    bolt_clear = bolt_r + 2.0        # 5.25 mm from bolt center (2 mm past hole wall)
    arm_buf    = 2.0                 # buffer past arm flange edge

    arm_y_min = y_center - flange_w / 2  # 22.0 mm
    arm_y_max = y_center + flange_w / 2  # 28.0 mm

    pkt_z0 = min(bz_coords) + bolt_clear   # 5.25 mm
    pkt_z1 = max(bz_coords) - bolt_clear   # 54.75 mm

    # Left pocket
    lpkt_y0 = min(by_coords) + bolt_clear      # 5.25 mm
    lpkt_y1 = arm_y_min - arm_buf              # 20.0 mm
    if lpkt_y1 > lpkt_y0 + 2.0 and pkt_z1 > pkt_z0 + 2.0:
        left_pocket = BRepPrimAPI_MakeBox(
            gp_Pnt(0.0, lpkt_y0, pkt_z0),
            gp_Pnt(pocket_depth, lpkt_y1, pkt_z1),
        ).Shape()
        cut_op = BRepAlgoAPI_Cut(shape, left_pocket)
        cut_op.Build()
        shape = cut_op.Shape()

    # Right pocket
    rpkt_y0 = arm_y_max + arm_buf              # 30.0 mm
    rpkt_y1 = max(by_coords) - bolt_clear      # 54.75 mm
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
