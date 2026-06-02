"""
Frame-plate bracket: perimeter frame + tall vertical spine.

Once the I-beam arm is near its analytical minimum, the 3 mm solid mounting plate
(~17.5 g) is the dominant mass target. This design hollows the plate interior while
keeping only what carries load: two bolt-zone bars (top/bottom), two side bars, and
a central vertical spine that extends to the full arm height.

Frame topology (YZ view, X is the arm direction):

  h_root ─ ┊                  ┊           ─  spine cap (z = z1 … h_root)
  z1     ┌──────────────────────────────────┐  top bar (z = z1-bar_w … z1)
     │    [bolt]             [bolt]     │
     ├──┤           ┊           ├───────┤  left/right bars (inner span)
     │  │           ┊           │       │
     │  │   vert spine at y_c   │       │
     │  │           ┊           │       │
     ├──┤           ┊           ├───────┤
     │    [bolt]    ┊    [bolt]         │
  z0 └──────────────────────────────────┘  bot bar (z = z0 … z0+bar_w)
     y0                                y1
                   y_center

Root cause of previous FEA failure (32.2–32.6 MPa):
  The spine stopped at inner_z1=52.75 mm. The arm root extends to h_root=90 mm.
  The 37.25 mm gap between spine top (52.75) and arm top (90) left the arm upper
  portion with only the 12 mm bolt bar at z=52.75–64.75 for lateral support. Above
  z=64.75 the arm is completely unsupported by the plate — the C3D4 FEA concentrates
  stress at the arm/top-bar junction, exceeding 25 MPa even after a mid-bar at z=25 mm.

Fix: extend spine from inner_z0 to h_root=90 mm. The spine now runs continuously from
  z=7.25 to z=90 mm, fully enclosing the arm root from bottom to top. No unsupported
  arm region above the top bolt bar.

bar_w = 13 mm: 8% wider than previous 12mm. Reduces bending stress by ~8%.
  FEA at 12mm: 26.1 MPa (just over 25.0 limit). Expected at 13mm: ~24.1 MPa ✓
plate_t = 3 mm (proven minimum for bolt-hole FEA stress in taper-beam and lean-arm)

Arm: unchanged from lean-arm (h_root=90 mm, h_tip=15 mm, web_w=2 mm,
     flange_w=6 mm, flange_t=1.5 mm). σ_max=14.84 MPa < 25 MPa ✓

Mass estimate (PLA, 1.24 g/cm³):
  Bot bar    (69.5 × 13 × 3)             ≈  2 711 mm³  ( 3.4 g)
  Top bar    (69.5 × 13 × 3)             ≈  2 711 mm³  ( 3.4 g)
  Left bar   (13 × 45.5 × 3)             ≈  1 775 mm³  ( 2.2 g)
  Right bar  (13 × 45.5 × 3)             ≈  1 775 mm³  ( 2.2 g)
  Spine      (13 × 82.75 × 3)            ≈  3 227 mm³  ( 4.0 g)
  Minus 4 bolt holes                      ≈   −398 mm³  (−0.5 g)
  Frame net                               ≈ 11 801 mm³  (14.6 g)
  Arm (web + flanges, lean-arm dims)      ≈ 12 636 mm³  (15.7 g)
  Total (overlaps reduce actual ~5 %)     ≈ 24 437 mm³  (~29.8 g)

  vs lean-arm (32.64 g verified SOTA):  −8.7 %
  vs taper-slim (34.10 g):              −12.6 %
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
    bar_w = 13.0                      # frame bar width; 13mm reduces stress ~8% vs 12mm

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

    # Arm dimensions — needed to set spine height.
    h_root = 90.0

    # Vertical spine: centred on arm y, spans from inner_z0 all the way to h_root.
    # Extending to h_root is the critical fix: the arm root goes to z=90 mm while the
    # top bolt bar only reaches z=64.75 mm. Without this extension the arm is laterally
    # unsupported from z=64.75 to z=90 mm, causing >25 MPa stress concentration.
    vert_spine = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, y_center - spine_half, inner_z0),
        gp_Pnt(plate_t, y_center + spine_half, h_root),
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

    # --- I-beam arm (lean-arm dimensions) ---
    web_w    = 2.0
    flange_w = 6.0
    flange_t = 1.5
    h_tip    = 15.0
    # h_root already defined above (= 90.0) for spine height.

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
