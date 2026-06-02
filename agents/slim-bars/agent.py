"""
Slim-bars bracket: H-frame topology with narrowed non-bolt bars.

Bolt bars (top/bottom) stay 12 mm wide — minimum for bolt-hole clearance.
All other bars (side bars, spine, mid-bar) are 8 mm — no bolt holes, no constraint.

Frame topology (YZ view, X is the arm direction):

  z1 ┌──────────────────────────────────────┐  top bolt bar   bar_w_bolt=12 mm
     │   [bolt]                   [bolt]   │
     ├─┤                  ┊           ├────┤  side bars (8 mm)
     │ │                  ┊           │    │
     │ ├──────────────────┼───────────┤    │  mid-bar at z=lp[2] (8 mm)
     │ │   spine at y_c   ┊           │    │
     │ │                  ┊           │    │
     ├─┤                  ┊           ├────┤
     │   [bolt]           ┊   [bolt]       │
  z0 └──────────────────────────────────────┘  bot bolt bar   bar_w_bolt=12 mm
     y0                                    y1

Bolt clearance (bolt bars):
  margin = bolt_r + 1.5 = 3.25 + 1.5 = 4.75 mm from plate edge to bolt centre
  bar_w_bolt = 12 mm → net past hole edge = 12 − 4.75 − 3.25 = 4.0 mm ✓

Side bars / spine / mid-bar (no bolt holes):
  bar_w_side = 8 mm — carries lateral stiffness; no bolt stress constraint.
  spine_w = 8 mm ≥ arm flange_w + 2 mm margin = 6 + 2 = 8 mm ✓
  Arm flanges (±3 mm from y_center) fully enclosed within spine (±4 mm). ✓

Spine height: spine extends from inner_z0=7.25 mm all the way to h_root=90 mm.
Root cause of frame-plate FEA failures (32.2–32.6 MPa): spine stopped at inner_z1=52.75 mm
while arm root reaches z=90 mm — the arm was unsupported from z=64.75 to z=90 mm, causing
stress concentration at the arm/top-bar junction regardless of the mid-bar at z=25 mm.
The extended spine provides a continuous load path: arm top → spine → top bolt bar → wall.

Mid-bar at z=lp[2]=25 mm adds lateral bracing of the side/spine at load height.

Mass estimate (PLA, 1.24 g/cm³):
  Bot bolt bar  (69.5 × 12 × 3 − 2 bolt holes) ≈  2 303 mm³  ( 2.9 g)
  Top bolt bar  (69.5 × 12 × 3 − 2 bolt holes) ≈  2 303 mm³  ( 2.9 g)
  Left bar      ( 8   × 45.5 × 3)               ≈  1 092 mm³  ( 1.4 g)
  Right bar     ( 8   × 45.5 × 3)               ≈  1 092 mm³  ( 1.4 g)
  Mid-bar       (69.5 ×  8 × 3 − overlaps)      ≈  1 092 mm³  ( 1.4 g)
  Spine         ( 8   × 82.75 × 3)              ≈  1 986 mm³  ( 2.5 g)
  Minus 4 bolt holes                             ≈   −299 mm³  (−0.4 g)
  Frame net                                      ≈  9 569 mm³  (11.9 g)
  Arm (lean-arm, web + flanges)                  ≈ 12 636 mm³  (15.7 g)
  Total (overlaps reduce actual ~5 %)            ≈ 22 205 mm³  (27.5 g)

  vs frame-plate (~28.6 g est.): −3.8 %
  vs lean-arm  (32.64 g SOTA):  −15.7 %
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for a slim-bars wall bracket."""
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
    margin = bolt_r + 1.5             # 4.75 mm — full clearance past hole edge

    plate_t = 3.0                     # x-thickness: proven minimum for bolt-hole FEA
    bar_w_bolt = 12.0                 # bolt bar width: maintains 4.0 mm net past hole edge
    bar_w_side = 8.0                  # side bar / spine width: no bolt holes, can be narrower

    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    y_center = lp[1]                  # 25 mm — arm attachment axis
    spine_half = bar_w_side / 2.0    # spine ±4 mm from y_center; flanges are ±3 mm ✓

    arm_len = lp[0] + 8.0            # 108 mm — 8 mm past load point

    # Inner z-span (between the two bolt bars).
    inner_z0 = plate_z0 + bar_w_bolt
    inner_z1 = plate_z1 - bar_w_bolt

    def box(p0, p1):
        return BRepPrimAPI_MakeBox(gp_Pnt(*p0), gp_Pnt(*p1)).Shape()

    def fuse(a, b):
        op = BRepAlgoAPI_Fuse(a, b)
        op.Build()
        return op.Shape()

    # --- Frame: bolt bars (full y-width, 12 mm, proven clearance) ---
    bot_bar = box(
        (0.0, plate_y0, plate_z0),
        (plate_t, plate_y1, plate_z0 + bar_w_bolt),
    )
    top_bar = box(
        (0.0, plate_y0, plate_z1 - bar_w_bolt),
        (plate_t, plate_y1, plate_z1),
    )

    # --- Frame: side bars (8 mm, no bolt holes) ---
    left_bar = box(
        (0.0, plate_y0, inner_z0),
        (plate_t, plate_y0 + bar_w_side, inner_z1),
    )
    right_bar = box(
        (0.0, plate_y1 - bar_w_side, inner_z0),
        (plate_t, plate_y1, inner_z1),
    )

    # --- I-beam arm dimensions (needed for spine height) ---
    h_root   = 90.0

    # Spine: 8 mm wide, extends from inner_z0 all the way to h_root.
    # Critical: arm root reaches z=90 mm; top bolt bar only reaches z=64.75 mm.
    # Spine must cover the full arm height or the arm is unsupported above z=64.75 mm.
    vert_spine = box(
        (0.0, y_center - spine_half, inner_z0),
        (plate_t, y_center + spine_half, h_root),
    )

    # Horizontal mid-bar: full y-width, 8 mm tall, centred on load point z.
    # Adds lateral bracing at load height; does not fix the arm-top stress issue
    # (that is handled by the extended spine above).
    load_z = lp[2]                        # 25 mm
    mid_bar = box(
        (0.0, plate_y0, load_z - bar_w_side / 2),
        (plate_t, plate_y1, load_z + bar_w_side / 2),
    )

    frame = fuse(bot_bar, top_bar)
    frame = fuse(frame, left_bar)
    frame = fuse(frame, right_bar)
    frame = fuse(frame, vert_spine)
    frame = fuse(frame, mid_bar)

    # --- I-beam arm ---
    web_w    = 2.0
    flange_w = 6.0
    flange_t = 1.5
    # h_root already defined above (= 90.0).
    h_tip    = 15.0

    bot_flange = box(
        (0.0, y_center - flange_w / 2, 0.0),
        (arm_len, y_center + flange_w / 2, flange_t),
    )

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

    arm = fuse(bot_flange, web)
    arm = fuse(arm, top_flange)

    shape = fuse(frame, arm)

    # Drill bolt holes through the mounting plate.
    for bby, bbz in bolt_pattern:
        axis = gp_Ax2(gp_Pnt(-1.0, bby, bbz), gp_Dir(1.0, 0.0, 0.0))
        hole = BRepPrimAPI_MakeCylinder(axis, bolt_r, plate_t + 2.0).Shape()
        cut_op = BRepAlgoAPI_Cut(shape, hole)
        cut_op.Build()
        shape = cut_op.Shape()

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
    z0_far: float,  z1_far: float,
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
