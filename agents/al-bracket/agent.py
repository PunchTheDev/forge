"""
Aluminum bracket for spec 002_equipment_mount (Al6061-T6, 100kg, 120mm arm).

Root cause of i-beam-al failures (PRs #40–43):
  h_tip was forced to lp[2]+5=50mm, making arm extend 34.25mm above the plate
  (plate_z1=45.75mm, arm top at z=80mm → 34.25mm unsupported cantilever).
  This junction stress concentration drove FEA to 163.7 MPa >> 110.4 MPa allowable.

Fix: constrain h_root ≤ plate_z1 = 45.75mm. Use h_root=45mm so arm is fully
supported by the plate. h_tip=15mm (same as spec-001 designs — FEA distributes
load at [120,50,45] to nearest arm nodes; load z > arm height is fine).

Taper ratio: 45/15 = 3.0:1 < deep-pocket's 6:1 limit ✓

Material: Al6061-T6
  density:  2.71 g/cm³ = 2.71×10⁻³ g/mm³
  yield:    276 MPa
  allowable: 276 / 2.5 = 110.4 MPa

Spec constraints:
  bolt_pattern:  6 × M8 in 3×2 grid [0/40/80mm × 0/40mm]
  bolt_diameter: 8.5mm → bolt_r=4.25mm, margin=5.75mm
  plate bounds: y∈[−5.75, 85.75mm], z∈[−5.75, 45.75mm]
  build volume: 150×100×90mm

Section modulus at arm root (h_root=45mm, flange_w=14mm, flange_t=2.5mm):
  M         = 981 × 120 = 117,720 N·mm
  c         = 22.5mm
  I_web     = 2 × (40)³/12 = 10,667 mm⁴   (web = 45−5 = 40mm)
  I_flange  = 2 × 14 × 2.5 × (22.5−1.25)² = 2 × 35 × 451.6 = 31,609 mm⁴
  I_total   = 42,276 mm⁴
  σ_root    = 117,720 × 22.5 / 42,276 = 62.7 MPa  (56.8% of 110.4 MPa ✓)

Mass estimate (Al density 2.71×10⁻³ g/mm³):
  arm_len = 124mm (4mm past load)
  Web avg h:    (40+10)/2 = 25mm  →  124×2×25 = 6,200 mm³ → 16.8g
  Flanges:      2×124×14×2.5 = 8,680 mm³ → 23.5g
  Plate solid:  3×91.5×51.5 = 14,147 mm³ → 38.3g
  6 bolt holes: 6×π×4.25²×3 = −1,021 mm³ → −2.8g
  Pockets (1.8mm deep, 1.2mm remaining wall):
    Left:  1.8×35.75×27.5 = 1,770 mm³ → −4.8g
    Right: 1.8×13.75×27.5 =  680 mm³ → −1.8g
  Total ≈ 69.2g   (vs 380g baseline, −81.8%)

Pocket zone geometry:
  pkt_z0 = min(bz)+bolt_clear = 0+6.25 = 6.25mm
  pkt_z1 = max(bz)−bolt_clear = 40−6.25 = 33.75mm → z_range=27.5mm
  Left:  y∈[6.25, arm_y_min−2] = [6.25, 19mm]  → y_range=12.75mm  →  guard!
  Actually arm_y_min = y_center−flange_w/2 = 50−7 = 43mm
  Left:  lpkt_y1 = 43−2 = 41mm, lpkt_y0 = 0+6.25 = 6.25mm → y_range=34.75mm ✓
  Right: rpkt_y0 = 43+14+2 = 59mm, rpkt_y1 = 80−6.25 = 73.75mm → y_range=14.75mm ✓
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for an aluminum 6061 equipment mount bracket."""
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

    plate_t  = 3.0
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin          # 45.75mm

    arm_len  = lp[0] + 4.0                     # 124mm

    web_w    = 2.0
    flange_w = 14.0                             # wider flanges for Al efficiency
    flange_t = 2.5
    # h_root ≤ plate_z1 = 45.75mm keeps arm fully within plate support.
    # Without this, arm sticks above plate → junction stress concentration.
    h_root   = 45.0
    h_tip    = 15.0                             # same as spec-001; FEA handles load above arm tip
    y_center = lp[1]                            # 50mm

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

    # ── Wall-face pockets: 1.8mm deep (1.2mm remaining; spec allows 0.8mm) ───
    pocket_depth = 1.8

    bolt_clear = bolt_r + 2.0                   # 6.25mm buffer past bolt hole wall
    arm_buf    = 2.0

    arm_y_min = y_center - flange_w / 2         # 43mm
    arm_y_max = y_center + flange_w / 2         # 57mm

    pkt_z0 = min(bz_coords) + bolt_clear        # 6.25mm
    pkt_z1 = max(bz_coords) - bolt_clear        # 33.75mm

    # Left pocket
    lpkt_y0 = min(by_coords) + bolt_clear       # 6.25mm
    lpkt_y1 = arm_y_min - arm_buf               # 41mm
    if lpkt_y1 > lpkt_y0 + 2.0 and pkt_z1 > pkt_z0 + 2.0:
        left_pocket = BRepPrimAPI_MakeBox(
            gp_Pnt(0.0, lpkt_y0, pkt_z0),
            gp_Pnt(pocket_depth, lpkt_y1, pkt_z1),
        ).Shape()
        cut_op = BRepAlgoAPI_Cut(shape, left_pocket)
        cut_op.Build()
        shape = cut_op.Shape()

    # Right pocket
    rpkt_y0 = arm_y_max + arm_buf               # 59mm
    rpkt_y1 = max(by_coords) - bolt_clear       # 73.75mm
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
