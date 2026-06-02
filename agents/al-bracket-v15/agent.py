"""
Al-bracket v15: hollow box arm (replaces I-beam).

Baseline: al-bracket v13 (PR #82): plate_t=1.5mm, fw=5mm, h_root=32mm. 35.276g, 47.54 MPa.

Parametric limits hit: plate_t=1.5mm floor, fw=5mm floor at h_root=32mm,
  h_root=31mm + fw=5mm always fails. All I-beam params exhausted.

Topology change: replace I-beam arm with hollow box arm (uniform cross-section).

Design:
  - Outer box: fw=5mm wide, h=32mm tall, arm_len=121mm long
  - Inner void: (fw-2t) × (h-2t) = 3.4mm × 30.4mm, starting at x=plate_t
    (solid cap at x=[0, plate_t] for plate attachment)
  - t_wall = min_wall = 0.8mm

Section comparison at h=32mm, fw=5mm:
  I-beam: A=66.8mm², I=6630mm⁴, c=16mm
  Hollow box: A=56.6mm², I=(5×32³-3.4×30.4³)/12=5693mm⁴, c=16mm
  σ_box = 47.54 × (6630/5693) = 55.3 MPa < 110.4 MPa ✓ (50%)

Mass estimate vs v13 (35.276g):
  I-beam arm mass (approx, fw=5mm, tapered h32→30mm):
    Flanges: 2×(121×5×0.8)×2.7e-3 = 2.61g
    Web: 121×2×(avg_h-1.6=29.4)×2.7e-3 = 19.21g
    Total: ~21.8g
  Hollow box arm mass (uniform h=32mm):
    Net area: 56.6mm²
    Hollow part (x=plate_t to arm_len): 56.6×119.5×2.7e-3 = 18.27g
    Solid cap (x=0 to plate_t): 160×1.5×2.7e-3 = 0.65g
    Total: ~18.92g
  Savings: ~2.9g → target ~32.4g

No taper: h=32mm constant. Load node: h(120)=32mm, |32-45|=13mm < 15mm ✓
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for al-bracket v15 (hollow box arm, targeting ~32.4g)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d = c["bolt_diameter_clearance_mm"]   # 8.5mm → bolt_r=4.25mm
    lp = c["load_point_mm"]                    # [120, 50, 45]
    min_wall = c.get("min_wall_thickness_mm", 0.8)

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    bolt_r = bolt_d / 2.0
    margin = bolt_r + min_wall                  # 5.05mm

    plate_t  = 1.5   # proven floor
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin          # 45.05mm

    arm_len  = lp[0] + 1.0                     # 121mm
    fw       = 5.0                              # proven OK with h=32mm
    h        = 32.0                             # uniform (no taper); h(120)=32, |32-45|=13<15 ✓
    t_wall   = min_wall                         # 0.8mm
    y_center = lp[1]                            # 50mm

    # ── Hollow box arm ──────────────────────────────────────────────────────
    # Outer solid box
    outer_arm = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, y_center - fw / 2, 0.0),
        gp_Pnt(arm_len, y_center + fw / 2, h),
    ).Shape()

    # Inner void (starts at x=plate_t; solid cap at x=[0, plate_t] for plate bond)
    inner_void = BRepPrimAPI_MakeBox(
        gp_Pnt(plate_t, y_center - fw / 2 + t_wall, t_wall),
        gp_Pnt(arm_len, y_center + fw / 2 - t_wall, h - t_wall),
    ).Shape()

    cut1 = BRepAlgoAPI_Cut(outer_arm, inner_void)
    cut1.Build()
    arm_shape = cut1.Shape()

    # ── Mounting plate ────────────────────────────────────────────────────────
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

    # ── Wall-face pockets: 0.7mm deep (plate_t=1.5, min_wall=0.8) ────────────
    pocket_depth = plate_t - min_wall           # 0.7mm
    bolt_clear   = bolt_r + 2.0 * min_wall     # 5.85mm (proven safe)
    arm_buf      = 2.0

    arm_y_min = y_center - fw / 2              # 47.5mm
    arm_y_max = y_center + fw / 2              # 52.5mm

    pkt_z0 = min(bz_coords) + bolt_clear
    pkt_z1 = max(bz_coords) - bolt_clear

    # Left pocket (between left plate edge and arm)
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

    # Right pocket (between arm and right plate edge)
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
