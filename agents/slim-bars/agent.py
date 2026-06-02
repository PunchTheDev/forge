"""
Slim-bars bracket: frame-plate topology with narrowed non-bolt bars.

The frame-plate design has 5 bars: two bolt bars (top/bottom) + two side bars (left/right)
+ a central spine. Only the bolt bars contain bolt holes — the side bars and spine are
bolt-free and can be narrower than the 12 mm bolt-clearance minimum.

Frame topology (YZ view):

  z1 ┌──────────────────────────────────────┐  top bolt bar   bar_w_bolt=12 mm
     │   [bolt]                   [bolt]   │
     ├─┤                  ┊           ├────┤  side bars (8 mm) + gap + spine (8 mm)
     │ │                  ┊           │    │
     │ │     spine at y_c ┊           │    │
     │ │                  ┊           │    │
     ├─┤                  ┊           ├────┤
     │   [bolt]           ┊   [bolt]       │
  z0 └──────────────────────────────────────┘  bot bolt bar   bar_w_bolt=12 mm
     y0                                    y1

Bolt clearance (bolt bars):
  margin = bolt_r + 1.5 = 3.25 + 1.5 = 4.75 mm from plate edge to bolt centre
  bar_w_bolt = 12 mm → net past hole edge = 12 − 4.75 − 3.25 = 4.0 mm ✓

Side bars (no bolt holes):
  bar_w_side = 8 mm — carries lateral stiffness; no bolt stress constraint.

Spine (no bolt holes):
  spine_w = 8 mm ≥ arm flange_w + 2 mm margin = 6 + 2 = 8 mm ✓
  Arm flanges (±3 mm from y_center) are fully enclosed within spine (±4 mm). ✓

Load path: arm root fuses into bolt bars (arm web spans full z height and
passes through both top and bottom bolt bar regions) + spine transfers some
arm root moment to bolt bars. Side bars provide lateral stiffness.

Arm: unchanged from lean-arm (h_root=90 mm, h_tip=15 mm, web_w=2 mm,
     flange_w=6 mm, flange_t=1.5 mm). σ_max=14.84 MPa < 17.5 MPa ✓

Mass estimate (PLA, 1.24 g/cm³):
  Bot bolt bar  (69.5 × 12 × 3 − 2 bolt holes) ≈  2 303 mm³  ( 2.9 g)
  Top bolt bar  (69.5 × 12 × 3 − 2 bolt holes) ≈  2 303 mm³  ( 2.9 g)
  Left bar      ( 8   × 45.5 × 3)               ≈  1 092 mm³  ( 1.4 g)
  Right bar     ( 8   × 45.5 × 3)               ≈  1 092 mm³  ( 1.4 g)
  Spine         ( 8   × 45.5 × 3)               ≈  1 092 mm³  ( 1.4 g)
  Frame net                                      ≈  7 882 mm³  ( 9.8 g)
  Arm (lean-arm, web + flanges)                  ≈ 12 636 mm³  (15.7 g)
  Total                                          ≈ 20 518 mm³  (25.4 g)

  vs frame-plate (~27.5 g est.): −7.6 %
  vs lean-arm  (32.64 g SOTA):  −22.2 %
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

    # --- Spine (8 mm, centred on arm y, fully encloses arm flanges) ---
    vert_spine = box(
        (0.0, y_center - spine_half, inner_z0),
        (plate_t, y_center + spine_half, inner_z1),
    )

    frame = fuse(bot_bar, top_bar)
    frame = fuse(frame, left_bar)
    frame = fuse(frame, right_bar)
    frame = fuse(frame, vert_spine)

    # --- I-beam arm (lean-arm dimensions, analytically verified) ---
    web_w    = 2.0
    flange_w = 6.0
    flange_t = 1.5
    h_root   = 90.0
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
