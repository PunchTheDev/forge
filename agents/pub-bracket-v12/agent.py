"""
pub-bracket-v12: Frame-plate optimization for pub_002_medium (Al6061, 32 kg @ 126 mm).

Builds on v6 (35.78g, 63.2 MPa, 45.8% utilization). The mounting plate is the
main mass target — replacing it with a frame plate (perimeter strips only) cuts
~6g from the plate with no impact on the arm stress path.

pub_002_medium parameters:
  load_point:   [125.6, 43.4, 44.5]
  bolt_pattern: [(0,0),(45.9,0),(0,45.9),(45.9,45.9)] — 45.9mm span
  bolt_d:       6.5mm → bolt_r = 3.25mm
  min_wall:     1.2mm
  build_vol:    [144.2, 86.8, 89.1]
  material:     Al6061-T6, yield=276 MPa, allowable=138 MPa (SF=2.0)

Frame plate design:
  strip_w = bolt_r + min_wall = 3.25 + 1.2 = 4.45mm
  plate exterior: 54.8mm × 54.8mm = 3,003 mm²
  interior cutout: 45.9mm × 45.9mm = 2,107 mm²
  frame area: 896 mm² (vs 3,003 mm² solid)
  Mass savings: (3,003 - 896) × 1.2mm × 2.71e-3 ≈ 6.8g

  Arm: unchanged from v6 (fw=4mm, h=31mm, hollow box) — ~27g
  Frame plate: ~2.5g  (was ~8.9g solid)
  Total estimate: ~29.5g  (saves ~6g vs v6's 35.78g)

Stress path: bolt columns at y=0 and y=45.9mm. Arm centered at y=43.4mm (load
point), its right face at y=45.4mm ≈ bolt col y=45.9mm. Frame plate y-strips at
y=0 and y=45.9mm directly serve the bolt-column load paths — no plate bending.
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v12 (frame plate, Al6061 pub_002)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d = c["bolt_diameter_clearance_mm"]
    lp = c["load_point_mm"]
    min_wall = c.get("min_wall_thickness_mm", 1.2)

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    bolt_r = bolt_d / 2.0
    strip_w = bolt_r + min_wall   # 4.45mm

    plate_t = min_wall
    plate_y0 = min(by_coords) - strip_w
    plate_y1 = max(by_coords) + strip_w
    plate_z0 = min(bz_coords) - strip_w
    plate_z1 = max(bz_coords) + strip_w

    arm_len = lp[0] + 1.0
    fw = 4.0
    h = 31.0          # |31 - 44.5| = 13.5mm < 15mm load tolerance ✓
    t_wall = min_wall
    y_center = lp[1]  # 43.4mm — close to bolt col at y=45.9mm

    # Hollow box arm (unchanged from v6)
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

    # Frame plate: solid plate minus interior cutout
    # Keeps only perimeter strips of width strip_w around bolt rows/columns
    full_plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    # Interior cutout removes the plate between bolt rows and columns
    cutout_y0 = float(min(by_coords))   # 0.0
    cutout_y1 = float(max(by_coords))   # 45.9
    cutout_z0 = float(min(bz_coords))   # 0.0
    cutout_z1 = float(max(bz_coords))   # 45.9

    plate_cutout = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, cutout_y0, cutout_z0),
        gp_Pnt(plate_t, cutout_y1, cutout_z1),
    ).Shape()

    cut2 = BRepAlgoAPI_Cut(full_plate, plate_cutout)
    cut2.Build()
    plate_shape = cut2.Shape()

    fuse1 = BRepAlgoAPI_Fuse(arm_shape, plate_shape)
    fuse1.Build()
    shape = fuse1.Shape()

    # Bolt holes
    for bby, bbz in bolt_pattern:
        axis = gp_Ax2(gp_Pnt(-1.0, bby, bbz), gp_Dir(1.0, 0.0, 0.0))
        hole = BRepPrimAPI_MakeCylinder(axis, bolt_r, plate_t + 2.0).Shape()
        cut_op = BRepAlgoAPI_Cut(shape, hole)
        cut_op.Build()
        shape = cut_op.Shape()

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
