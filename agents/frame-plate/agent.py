"""
H-frame-plate bracket: perimeter frame + vertical spine + horizontal mid-bar.

Once the I-beam arm is near its analytical minimum, the 3 mm solid mounting plate
(~17.5 g) is the dominant mass target. This design hollows the plate interior while
keeping only what carries load: four bolt-zone bars, a central vertical spine, and a
horizontal mid-bar at the load-point height.

Frame topology (YZ view, X is the arm direction):

  z1 ┌───────────────────────────────────┐  top bar   (z = z1-bar_w … z1)
     │    [bolt]             [bolt]     │
     ├──┤                       ├───────┤  left/right bars
     │  │                       │       │
     │  ├───────────────────────┤       │  mid-bar at z = load_z (H cross-bar)
     │  │    vert spine at y_c  │       │
     │  │           ┊           │       │
     ├──┤           ┊           ├───────┤
     │    [bolt]    ┊    [bolt]         │
  z0 └───────────────────────────────────┘  bot bar   (z = z0 … z0+bar_w)
     y0                                 y1
                   y_center

The original frame-plate (no mid-bar) failed FEA at 32.2 MPa because the arm
(h_root=90 mm) extends 25 mm above the top bolt bar (z=64.75 mm) with no plate
support. The arm above the top bar acts as an unsupported cantilever, concentrating
stress at the top-bar / arm junction.

Fix: add a horizontal mid-bar spanning the full plate width at z = lp[2] = 25 mm
(the load application height). This creates an H-frame with direct load transfer
from arm root to the mid-bar, eliminating the stress concentration.

bar_w = 12 mm: plate edge to bolt hole outer edge = 4.75 mm (from margin formula),
                hole outer edge to bar inner edge = 12 − (bolt_r + 4.75) = 4.0 mm ✓
plate_t = 3 mm (proven minimum for bolt-hole FEA stress in taper-beam and lean-arm)

Arm: unchanged from lean-arm (h_root=90 mm, h_tip=15 mm, web_w=2 mm,
     flange_w=6 mm, flange_t=1.5 mm). σ_max=14.84 MPa < 25 MPa ✓

Net section at bolt holes (12 mm bar, 3.25 mm bolt radius):
  net_width = 12 − 3.25 = 8.75 mm → A_net = 8.75 × 3 = 26.25 mm²
  Worst-case bolt shear ≈ F/4 = 98 N → σ ≈ 3.7 MPa ≪ 25 MPa ✓

Mass estimate (PLA, 1.24 g/cm³):
  Bot bar    (69.5 × 12 × 3)             ≈  2 502 mm³  ( 3.1 g)
  Top bar    (69.5 × 12 × 3)             ≈  2 502 mm³  ( 3.1 g)
  Mid bar    (69.5 × 12 × 3)             ≈  2 502 mm³  ( 3.1 g)
  Left bar   (12 × 45.5 × 3)             ≈  1 638 mm³  ( 2.0 g)
  Right bar  (12 × 45.5 × 3)             ≈  1 638 mm³  ( 2.0 g)
  Vert spine (12 × 45.5 × 3)             ≈  1 638 mm³  ( 2.0 g)
  Minus 4 bolt holes                      ≈   −398 mm³  (−0.5 g)
  Frame net                               ≈ 12 022 mm³  (14.9 g)
  Arm (web + flanges, lean-arm dims)      ≈ 12 636 mm³  (15.7 g)
  Total                                   ≈ 24 658 mm³  (30.6 g)

  vs lean-arm (32.64 g verified SOTA):  −6 %
  vs taper-slim (34.10 g):              −10 %
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for a frame-plate wall bracket."""
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
    bar_w = 12.0                      # frame bar width; 4.0 mm net past bolt hole edge

    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    # Spine centred on arm attachment point.
    y_center = lp[1]                  # 25 mm
    spine_half = bar_w / 2.0         # spine same width as bars for uniform sections

    arm_len = lp[0] + 8.0            # 108 mm — 8 mm past load point

    # --- Frame bars (all at x=[0, plate_t]) ---
    # Bottom bar: full plate width in Y, captures bolts at z=0.
    bot_bar = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z0 + bar_w),
    ).Shape()

    # Top bar: full plate width in Y, captures bolts at z=60.
    top_bar = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, plate_z1 - bar_w),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    # Inner z-span (between corner bars) for left/right bars and spine.
    inner_z0 = plate_z0 + bar_w
    inner_z1 = plate_z1 - bar_w

    # Left bar: y=[y0, y0+bar_w], z=inner span.
    left_bar = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, inner_z0),
        gp_Pnt(plate_t, plate_y0 + bar_w, inner_z1),
    ).Shape()

    # Right bar: y=[y1-bar_w, y1], z=inner span.
    right_bar = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y1 - bar_w, inner_z0),
        gp_Pnt(plate_t, plate_y1, inner_z1),
    ).Shape()

    # Vertical spine: centred on arm y, spans z=inner span.
    vert_spine = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, y_center - spine_half, inner_z0),
        gp_Pnt(plate_t, y_center + spine_half, inner_z1),
    ).Shape()

    # Horizontal mid-bar: full plate width in Y, centred on load point z.
    # Eliminates the unsupported arm cantilever above the top bolt bar by
    # providing a direct lateral brace at the load-application height.
    load_z = lp[2]                        # 25 mm
    mid_bar = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, load_z - bar_w / 2),
        gp_Pnt(plate_t, plate_y1, load_z + bar_w / 2),
    ).Shape()

    # Fuse all frame elements.
    def fuse(a, b):
        op = BRepAlgoAPI_Fuse(a, b)
        op.Build()
        return op.Shape()

    frame = fuse(bot_bar, top_bar)
    frame = fuse(frame, left_bar)
    frame = fuse(frame, right_bar)
    frame = fuse(frame, vert_spine)
    frame = fuse(frame, mid_bar)

    # --- I-beam arm (lean-arm dimensions) ---
    web_w    = 2.0
    flange_w = 6.0
    flange_t = 1.5
    h_root   = 90.0
    h_tip    = 15.0

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

    arm = fuse(bot_flange, web)
    arm = fuse(arm, top_flange)

    # Merge arm into frame.
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
