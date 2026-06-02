"""
SS-bracket v3: reduce fw 12→8mm and plate_t 1.5→1.0mm.

Baseline: ss-bracket-v2b (PR #93): fw=12mm, h=80mm, t_wall=1.0mm, plate_t=1.5mm.
  279.15g, 49.63 MPa (60.5% of 82 MPa allowable).

Changes vs v2b:
  fw: 12mm → 8mm (inner void: 10→6mm, safely > MESH_SIZE=4mm, no convergence risk)
  plate_t: 1.5mm → 1.0mm (pocket_depth: 1.0→0.5mm)

Section modulus check (fw=8, h=80, t_wall=1.0mm):
  I = (8×80³ - 6×78³)/12 = (4,096,000 - 2,845,584)/12 = 104,201 mm⁴
  Z = 104,201/40 = 2,605 mm³ (vs min required 1,794 mm³ = 1.45× margin)
  M_max = 981 × 150 = 147,150 N·mm
  sigma_bending = 147,150/2,605 = 56.5 MPa
  Scaling from v2b (Z_v2b=2,919, FEA=49.63): 49.63×2919/2605 = 55.6 MPa
  Expected FEA: ~56 MPa (68% of 82 MPa) — below 70% convergence trigger ✓

Mass estimate vs v2b (279.15g):
  Arm (fw 12→8, t_wall=1.0): 28350→26440 mm³, saves ~15.3g
  Plate (plate_t 1.5→1.0, pocket_depth 1.0→0.5mm): saves ~12g
  Total target: ~252g
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for ss-bracket-v3 (fw=8mm, plate_t=1.0mm, target ~252g)."""
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

    plate_t  = 1.0                              # reduced from 1.5mm; saves ~12g
    plate_y0 = min(by_coords) - margin          # -5.75mm
    plate_y1 = max(by_coords) + margin          # 105.75mm
    plate_z0 = min(bz_coords) - margin          # -5.75mm
    plate_z1 = max(bz_coords) + margin          # 65.75mm

    arm_len  = lp[0] + 1.0                     # 151mm
    fw       = 8.0                              # reduced from 12mm; inner void=6mm > mesh_size ✓
    h        = 80.0                             # height in z; load at z=45 within span ✓
    t_wall   = 1.0                              # 2× min_wall: mesh resolves walls cleanly
    y_center = lp[1]                            # 50mm

    # ── Hollow box arm ──────────────────────────────────────────────────────────
    outer_arm = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, y_center - fw / 2, 0.0),
        gp_Pnt(arm_len, y_center + fw / 2, h),
    ).Shape()

    # Inner void starts at x=plate_t (solid cap for plate attachment)
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

    # ── Wall-face pockets (plate_t=1.0, min_wall=0.5 → pocket_depth=0.5mm) ───
    pocket_depth = plate_t - min_wall           # 0.5mm
    bolt_clear   = bolt_r + 2.0 * min_wall     # 6.25mm
    arm_buf      = 2.0

    arm_y_min = y_center - fw / 2              # 46mm
    arm_y_max = y_center + fw / 2              # 54mm

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
