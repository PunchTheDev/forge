"""
SS-bracket v6: reduce arm height h from 70mm to 60mm.

Baseline: ss-bracket-v5 (PR #99): fw=8mm, h=70mm, t_wall=1.0mm, plate_t=0.5mm.
  212.45g, 50.80 MPa (61.9% of 82 MPa allowable). Stress headroom: 38%.

Note: FEA stress came in well below beam-theory prediction at h=70.
The plate (z=0 to 65.75mm) provides substantial composite stiffening;
at h=70 arm and plate overlap for 65.75mm of their 70mm height.
At h=60, the arm is entirely within plate height → stiffening effect stronger.

Changes vs v5:
  h: 70mm → 60mm

Load node check: load at z=45, arm spans z=0 to 60 → load at 75% of arm height.
  Nodes near z=45 are well within arm interior. ✓

Section modulus check (fw=8, h=60, t_wall=1.0mm):
  I = (8×60³ - 6×58³)/12 = (1,728,000 - 1,169,928)/12 = 46,506 mm⁴
  Z = 46,506/30 = 1,550 mm³ (vs min required 1,794 mm³ — below beam theory)
  Beam-theory sigma = 147,150/1,550 = 94.9 MPa (above allowable)
  BUT: plate stiffening reduces effective stress. v5 actual/predicted = 50.8/62.9 = 0.808.
  Estimated FEA: 50.80 × (Z_v5/Z_v6) / 0.808² correction = complex.
  Direct scaling from v5 (FEA): 50.80 × 2028/1550 = 66.4 MPa (est.)
  But plate stiffening may further reduce this → could be 55-60 MPa.

Convergence check: trigger at >57.4 MPa. May or may not fire depending on actual stress.

Mass estimate vs v5 (212.45g):
  Arm cross-section: 8×70 - 6×68 = 152mm² → 8×60 - 6×58 = 132mm²
  Savings: 20mm² × 151mm × 7.99e-3 = 24.1g
  Target: ~212.45 - 24.1 = ~188.4g
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for ss-bracket-v6 (h=60mm, target ~188g)."""
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

    plate_t  = min_wall                         # 0.5mm = min_wall
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    arm_len  = lp[0] + 1.0                     # 151mm
    fw       = 8.0                              # inner void=6mm > mesh_size=4mm ✓
    h        = 60.0                             # reduced from 70mm; load at z=45 (75% of span) ✓
    t_wall   = 1.0                              # 2× min_wall: reliable FEA convergence
    y_center = lp[1]                            # 50mm

    # ── Hollow box arm ──────────────────────────────────────────────────────────
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

    # ── No pockets: plate_t=min_wall, pocket_depth=0 ─────────────────────────

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
