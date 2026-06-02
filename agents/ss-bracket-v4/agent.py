"""
SS-bracket v4: reduce plate_t to 0.5mm = min_wall (absolute floor).

Baseline: ss-bracket-v3 (PR #97): fw=8mm, h=80mm, t_wall=1.0mm, plate_t=1.0mm.
  252.04g, 44.87 MPa (54.7% of 82 MPa allowable). Stress headroom: 45%.

Changes vs v3:
  plate_t: 1.0mm → 0.5mm = min_wall (absolute minimum)
  pocket_depth: 0.5mm → 0mm (no pockets at minimum plate_t)

Mass estimate:
  Plate at plate_t=1.0mm (with 0.5mm pockets, 6 bolt holes): ~46g
  Plate at plate_t=0.5mm (no pockets, 6 bolt holes):
    Solid: 111.5×71.5×0.5 = 3,986mm³
    Bolt holes: 6×π×5.25²×0.5 = 259mm³
    Net: 3,727mm³ × 7.99e-3 = 29.8g
  Plate savings: ~16g
  Target: ~252 - 16 = ~236g

Stress: plate_t reduction minimally affects arm bending stress.
  arm stress dominated by fw=8, h=80 section → stays ~45 MPa.
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for ss-bracket-v4 (plate_t=0.5mm=min_wall, target ~236g)."""
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

    plate_t  = min_wall                         # 0.5mm = absolute minimum allowed
    plate_y0 = min(by_coords) - margin          # -5.75mm
    plate_y1 = max(by_coords) + margin          # 105.75mm
    plate_z0 = min(bz_coords) - margin          # -5.75mm
    plate_z1 = max(bz_coords) + margin          # 65.75mm

    arm_len  = lp[0] + 1.0                     # 151mm
    fw       = 8.0                              # inner void=6mm > mesh_size=4mm ✓
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

    # ── No pockets: plate_t=min_wall, pocket_depth=0 ─────────────────────────
    # pocket_depth = plate_t - min_wall = 0.0mm

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
