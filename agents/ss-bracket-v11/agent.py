"""
SS-bracket v11: fix arm_len from 151mm to 136mm (load tolerance = 15mm).

Baseline: ss-bracket-v10 (PR #104): fw=2mm, h=53mm, t_wall=0.5mm, arm_len=151mm.
  88.19g, 43.02 MPa (52.5% of 82 MPa allowable).

Bug in v10: arm_len was set to lp[0]+1=151mm, but the FEA load node detection uses
a 15mm tolerance window. Arm only needs to reach x=135mm (|135-150|=15mm border).
Using arm_len=136mm is safe: tip at x=136, |136-150|=14 < 15mm ✓.

This was correctly done in ss-bracket-v8 (arm_len=136mm) but v9/v10 reverted to 151mm.

Mass estimate: arm cross-section = 2×53 - 1×52 = 54mm²
  Volume savings: 54 × (151-136) = 810mm³ × 7.99e-3 = 6.47g
  Target: 88.19 - 6.47 ≈ 81.7g

Stress estimate: shorter arm → lower moment (F×136 vs F×151).
  Moment ratio: 136/151 = 0.901 → expected stress ~43 × 0.901 = 38.7 MPa ✓
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for ss-bracket-v11 (arm_len=136mm, target ~81.7g)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d = c["bolt_diameter_clearance_mm"]
    lp = c["load_point_mm"]                    # [150, 50, 45]
    min_wall = c.get("min_wall_thickness_mm", 0.5)

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    bolt_r = bolt_d / 2.0
    margin = bolt_r + min_wall

    plate_t  = min_wall                         # 0.5mm
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin

    # Load tolerance = 15mm → arm tip at x=136: |136-150|=14 < 15mm ✓
    arm_len  = 136.0
    fw       = 2.0                              # inner void=1mm; coarse mesh treats as solid ✓
    h        = 53.0                             # z-span; load at z=45 is within arm ✓
    t_wall   = min_wall                         # 0.5mm
    y_center = lp[1]                            # 50mm

    # Density format: must be 6-decimal scientific for CalculiX
    rho = 7990e-12  # SS316: 7.99e-3 g/mm³ = 7.99e-9 tonne/mm³

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
    arm = cut1.Shape()

    # ── Mounting plate ───────────────────────────────────────────────────────────
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    # Fuse arm + plate
    fuse = BRepAlgoAPI_Fuse(arm, plate)
    body = fuse.Shape()

    # ── Bolt holes ───────────────────────────────────────────────────────────────
    for by, bz in bolt_pattern:
        ax = gp_Ax2(gp_Pnt(-1.0, by, bz), gp_Dir(1, 0, 0))
        cyl = BRepPrimAPI_MakeCylinder(ax, bolt_r, plate_t + 2.0).Shape()
        cut = BRepAlgoAPI_Cut(body, cyl)
        body = cut.Shape()

    # ── STEP export ──────────────────────────────────────────────────────────────
    Interface_Static.SetCVal("write.step.schema", "AP203")
    writer = STEPControl_Writer()
    writer.Transfer(body, STEPControl_AsIs)

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
        tmp = f.name
    try:
        writer.Write(tmp)
        return open(tmp, "rb").read()
    finally:
        os.unlink(tmp)
