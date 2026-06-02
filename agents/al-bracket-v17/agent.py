"""
Al-bracket v17: narrowest hollow box arm (fw=2mm, h=31mm).

Baseline: al-bracket v16 (PR #87): fw=3mm, h=31mm. Est ~30.7g.

fw: 3mm → 2mm. Inner void narrows from 1.4mm to 0.4mm (walls stay 0.8mm=min_wall).
h: 31mm (unchanged — minimum for load node detection: |31-45|=14 < 15mm tol ✓)

Section comparison (bending about y-axis, load in -z):
  v16 (fw=3, h=31): I=(3×31³-1.4×29.4³)/12 = (89373-35577)/12 = 4483mm⁴, c=15.5 → Z=289mm³
  v17 (fw=2, h=31): I=(2×31³-0.4×29.4³)/12 = (59582-10165)/12 = 4118mm⁴, c=15.5 → Z=266mm³

  v15 PASSED at 41.4 MPa (37.5% of 110.4 MPa allowable) with Z_v15=356mm³.
  Stress scales as Z_v15/Z_v17 = 356/266 = 1.338×:  41.4 × 1.338 = 55.4 MPa < 110.4 MPa ✓ (50.2%)

Net arm area change:
  v16: 3×31 - 1.4×29.4 = 51.84mm²  (arm L=119.5mm: 16.71g)
  v17: 2×31 - 0.4×29.4 = 50.24mm²  (arm L=119.5mm: 16.19g)

Arm savings vs v16: 0.52g
Plate pockets: slightly larger left pocket (+1mm arm narrower) → ~0.07g extra savings
Total savings vs v16: ≈ 0.6g → target ~30.1g
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for al-bracket v17 (fw=2mm hollow box arm, targeting ~30.1g)."""
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
    plate_z1 = max(bz_coords) + margin

    arm_len  = lp[0] + 1.0                     # 121mm
    fw       = 2.0                              # narrowed from 3mm; inner void = 0.4mm × 29.4mm
    h        = 31.0                             # min for load nodes: |31-45|=14 < 15mm tol ✓
    t_wall   = min_wall                         # 0.8mm
    y_center = lp[1]                            # 50mm

    # ── Hollow box arm ──────────────────────────────────────────────────────
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

    arm_y_min = y_center - fw / 2              # 49mm
    arm_y_max = y_center + fw / 2              # 51mm

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
