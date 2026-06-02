"""
SS-bracket v1: stainless 316 hollow box arm for spec 003_pipe_clamp_bracket.

Baseline to beat: baseline_steel ~2799g (solid block).
This design: thin-walled hollow box arm + pocketed mounting plate.

Spec 003 constraints:
  material: stainless_316 (ρ=7.99e-3 g/mm³, σ_y=205 MPa, SF=2.5 → σ_allow=82 MPa)
  load: 981 N at [150, 50, 45] in -z
  bolt_pattern: 6×M10, y=[0,50,100], z=[0,60], bolt_r=5.25mm
  build_volume: 180×120×100mm, min_wall=0.5mm

Section sizing (hollow box, bending about y-axis):
  M_max = 981 × 150 = 147150 N·mm
  Required Z = I/c > M/σ_allow = 147150/82 = 1794 mm³

  fw=25, h=80, t=0.5mm:
    I = (25×80³ - 24×79³)/12 = (12800000 - 11832936)/12 = 80589 mm⁴
    Z = 80589/40 = 2015 mm³ > 1794 ✓  (1.12× margin)

  Expected stress: 147150 / 2015 = 73.0 MPa < 82 MPa ✓

Mass estimate (target):
  Arm: (25×80 - 24×79) × 151 × 7.99e-3 = 104 × 151 × 7.99e-3 ≈ 125.5g
  Plate (1.5mm, pocketed): ≈ 160g
  Total: ≈ 282g  (vs 2799g baseline = 10× improvement)
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for ss-bracket-v1 (hollow box arm, stainless 316)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d = c["bolt_diameter_clearance_mm"]   # 10.5mm → bolt_r=5.25mm
    lp = c["load_point_mm"]                    # [150, 50, 45]
    min_wall = c.get("min_wall_thickness_mm", 0.5)

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    bolt_r = bolt_d / 2.0
    margin = bolt_r + min_wall                  # 5.75mm

    plate_t  = 1.5
    plate_y0 = min(by_coords) - margin          # -5.75mm
    plate_y1 = max(by_coords) + margin          # 105.75mm
    plate_z0 = min(bz_coords) - margin          # -5.75mm
    plate_z1 = max(bz_coords) + margin          # 65.75mm

    arm_len  = lp[0] + 1.0                     # 151mm (load at x=150, ±15mm tol)
    fw       = 25.0                             # hollow box width in y
    h        = 80.0                             # hollow box height in z
    t_wall   = min_wall                         # 0.5mm (minimum wall)
    y_center = lp[1]                            # 50mm

    # ── Hollow box arm ──────────────────────────────────────────────────────────
    # Outer solid box, z from 0 to h (load at z=45 is within span, tol=15mm ✓)
    outer_arm = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, y_center - fw / 2, 0.0),
        gp_Pnt(arm_len, y_center + fw / 2, h),
    ).Shape()

    # Inner void starts at x=plate_t (solid cap at base for plate bond)
    inner_void = BRepPrimAPI_MakeBox(
        gp_Pnt(plate_t, y_center - fw / 2 + t_wall, t_wall),
        gp_Pnt(arm_len, y_center + fw / 2 - t_wall, h - t_wall),
    ).Shape()

    cut1 = BRepAlgoAPI_Cut(outer_arm, inner_void)
    cut1.Build()
    arm_shape = cut1.Shape()

    # ── Mounting plate ─────────────────────────────────────────────────────────
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    fuse1 = BRepAlgoAPI_Fuse(arm_shape, plate)
    fuse1.Build()
    shape = fuse1.Shape()

    # ── Bolt holes ────────────────────────────────────────────────────────────
    for bby, bbz in bolt_pattern:
        axis = gp_Ax2(gp_Pnt(-1.0, bby, bbz), gp_Dir(1.0, 0.0, 0.0))
        hole = BRepPrimAPI_MakeCylinder(axis, bolt_r, plate_t + 2.0).Shape()
        cut_op = BRepAlgoAPI_Cut(shape, hole)
        cut_op.Build()
        shape = cut_op.Shape()

    # ── Wall-face pockets: saves plate mass between bolt columns ───────────────
    # pocket_depth = plate_t - min_wall = 1.0mm
    pocket_depth = plate_t - min_wall
    bolt_clear   = bolt_r + 2.0 * min_wall     # 6.25mm (2 walls of clearance)
    arm_buf      = 2.0

    arm_y_min = y_center - fw / 2              # 37.5mm
    arm_y_max = y_center + fw / 2              # 62.5mm

    pkt_z0 = min(bz_coords) + bolt_clear
    pkt_z1 = max(bz_coords) - bolt_clear

    # Left pocket (between left bolt column y=0 and arm left edge)
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

    # Right pocket (between arm right edge and right bolt column y=100)
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
