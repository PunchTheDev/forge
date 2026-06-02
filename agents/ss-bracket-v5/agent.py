"""
SS-bracket v5: reduce arm height h from 80mm to 70mm.

Baseline: ss-bracket-v4 (PR #98): fw=8mm, h=80mm, t_wall=1.0mm, plate_t=0.5mm.
  236.82g, 48.94 MPa (59.7% of 82 MPa allowable). Stress headroom: 40%.

Changes vs v4:
  h: 80mm → 70mm (arm height in z-direction)

Load node check: load at z=45, arm spans z=0 to 70 → load at 64% of arm height.
  Nodes within 15mm of z=45 are abundant in arm interior. ✓

Section modulus check (fw=8, h=70, t_wall=1.0mm):
  I = (8×70³ - 6×68³)/12 = (2,744,000 - 1,892,352)/12 = 70,971 mm⁴
  Z = 70,971/35 = 2,028 mm³ (vs min required 1,794 mm³ = 1.13× margin)
  M_max = 981 × 150 = 147,150 N·mm
  sigma_bending = 147,150/2,028 = 72.6 MPa
  Scaling from v4 (Z_v4=2,605mm³, FEA=48.94 MPa): 48.94×2605/2028 = 62.9 MPa
  Expected FEA: ~63 MPa (76.7% of 82 MPa allowable).

Convergence check: triggers at >70% × 82 = 57.4 MPa.
  Expected ~63 MPa → convergence check WILL fire (fine mesh pass).
  Hollow box (fw=8, t_wall=1.0mm): inner void 6mm > mesh_size=4mm ✓
  t_wall=1.0mm (2×min_wall) ensures reliable FEA convergence.

Mass estimate vs v4 (236.82g):
  Arm cross-section: 8×80 - 6×78 = 172mm² → 8×70 - 6×68 = 152mm²
  Arm volume change: (172→152mm²) × 151mm = 3,020mm³ → saves 3,020×7.99e-3 = 24.1g
  Target: ~236.82 - 24.1 = ~212.7g
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for ss-bracket-v5 (h=70mm, target ~213g)."""
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
    h        = 70.0                             # reduced from 80mm; load at z=45 (64% of span) ✓
    t_wall   = 1.0                              # 2× min_wall: mesh resolves walls cleanly
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
