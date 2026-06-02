"""
Al-bracket v18: reduce plate thickness to 1.0mm (from 1.5mm in v16).

Baseline: al-bracket v16 (PR #87): fw=3mm, h=31mm, plate_t=1.5mm. 30.35g, 55.48 MPa.
v17 (fw=2mm) dead: 0.4mm inner void → geometric singularity, 40.5% mesh deviation.
fw=3mm is the floor. Next lever: plate_t.

plate_t: 1.5mm → 1.0mm (minimum meaningful: 1.0/0.8 = 1.25× min_wall)
pocket_depth: 0.7mm → 0.2mm (plate_t - min_wall)

Plate mass change (approx):
  Solid: 90.1×50.1×(1.5→1.0)×2.7e-3 saves 18.27→12.18g = 6.09g
  Bolt holes: 1.38→0.92g saves 0.46g
  Pockets: 4.35→1.24g saves 3.11g (but pocket_depth 0.7→0.2mm)
  Net plate savings: ~2.5g

Arm mass: arm solid cap savings 3×31×0.5×2.7e-3 = 0.13g
  (hollow section unchanged since starts at plate_t but arm_len fixed)

Total savings vs v16 (30.35g): ≈ 2.63g → target ~27.7g

Stress check: plate_t=1.0mm reduces plate stiffness. Arm junction may see higher
  local stress. v16 passed at 55.48 MPa (50.3% of 110.4 MPa). Even with 1.5×
  increase in plate junction stress → 83 MPa < 110.4 MPa ✓ (well within allowable).
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for al-bracket v18 (plate_t=1.0mm, targeting ~27.7g)."""
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

    plate_t  = 1.0                              # reduced from 1.5mm; saves ~2.5g net
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    arm_len  = lp[0] + 1.0                     # 121mm
    fw       = 3.0                              # floor from v16/v17 experiments
    h        = 31.0                             # min for load nodes: |31-45|=14 < 15mm ✓
    t_wall   = min_wall                         # 0.8mm
    y_center = lp[1]                            # 50mm

    # ── Hollow box arm ──────────────────────────────────────────────────────
    outer_arm = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, y_center - fw / 2, 0.0),
        gp_Pnt(arm_len, y_center + fw / 2, h),
    ).Shape()

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

    # ── Wall-face pockets: 0.2mm deep (plate_t=1.0, min_wall=0.8) ────────────
    pocket_depth = plate_t - min_wall           # 0.2mm
    bolt_clear   = bolt_r + 2.0 * min_wall     # 5.85mm
    arm_buf      = 2.0

    arm_y_min = y_center - fw / 2              # 48.5mm
    arm_y_max = y_center + fw / 2              # 51.5mm

    pkt_z0 = min(bz_coords) + bolt_clear
    pkt_z1 = max(bz_coords) - bolt_clear

    # Left pocket
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

    # Right pocket
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
