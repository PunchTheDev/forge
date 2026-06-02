"""
Al-bracket v19: reduce plate thickness to 0.8mm (= min_wall, theoretical floor).

Baseline: al-bracket v18b (PR #94): fw=3mm, h=31mm, plate_t=1.0mm. 27.13g, 34.90 MPa.
Note: prior "plate_t=1.5mm floor" was for I-beam arm, NOT hollow box. v18b proves
  plate_t=1.0mm works with hollow box arm, at only 31.6% of allowable stress.

plate_t: 1.0mm → 0.8mm (= min_wall, the absolute minimum allowed)
pocket_depth: 0.2mm → 0mm (no pockets at minimum plate_t)

Plate mass change vs v18b (plate_t=1.0mm):
  Solid: 90.1×50.1×(1.0→0.8)×2.7e-3 saves 12.18→9.74g = 2.44g
  Bolt holes: 0.92→0.74g saves 0.18g
  Pockets: 1.24→0g (pocket_depth=0, no pockets) — loses 1.24g
  Net plate savings: ~1.38g

Arm solid cap: 3×31×(1.0→0.8)×2.7e-3 saves 0.05g

Total savings vs v18b (27.13g): ≈ 1.43g → target ~25.7g

Stress check: v18b at 34.90 MPa (31.6% of 110.4 MPa). With plate_t=0.8mm:
  Stress scales roughly as 1/plate_t (thinner plate = more flexible = less load)
  or possibly 1/plate_t² (bending-dominated). Either way, stress should remain well
  below 110.4 MPa allowable."""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for al-bracket v19 (plate_t=0.8mm=min_wall, targeting ~25.7g)."""
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

    plate_t  = min_wall                          # 0.8mm = absolute minimum allowed
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

    # ── Wall-face pockets: none at plate_t=min_wall (no material to remove) ────
    pocket_depth = plate_t - min_wall           # 0.0mm — no pockets at minimum plate_t

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
