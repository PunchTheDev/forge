"""
SS-bracket v14: stepped tapered arm.

Insights from previous versions:
- v10/v11 (uniform arm z=0-53, h=53mm): 88.19g — SOTA
- v12 (arm z=0-48, h=48mm): FAIL 209 MPa — arm TOP at z=48 enters load zone (z≈40-50)
  Load applied to arm-tip corner → singularity → catastrophic stress
- v13 (arm z=10-53, h=43mm from root): FAIL — plate section z=0-10 must bridge bolt-to-arm
  gap; creates plate stress concentration at arm base (z=10, x=0)

KEY CONSTRAINT: Arm TOP must be ≥ z=53 (3mm above load zone top z≈50).
KEY CONSTRAINT: Arm root (x=0) must reach z=0 to connect directly to lower bolt row (z=0).
 → Cannot raise root bottom. Can raise tip bottom (farther from bolt constraints).

SOLUTION: Stepped tapered arm.
  - Segment 0 (root, x=0-27):   z=0–53, h=53mm  ← FULL HEIGHT, z=0 bolt connection
  - Segment 1 (x=27-54):        z=6–53, h=47mm
  - Segment 2 (x=54-81):        z=12–53, h=41mm
  - Segment 3 (x=81-108):       z=18–53, h=35mm
  - Segment 4 (tip, x=108-136): z=24–53, h=29mm

All segments share TOP at z=53 (above load zone top z≈50) → no tip stress concentration ✓
Root seg at z=0-53 → lower bolt (z=0) directly connected ✓
Tip seg at z=24-53 → load zone z=40-50 fully within arm at x=136 ✓

Mass vs v10 (uniform h=53, arm volume 7,344mm³):
  Net cross-section = 2×h - 1×(h-1) = h+1  (fw=2, t_wall=0.5)
  Seg 0: (53+1) × 27 = 1,458mm³
  Seg 1: (47+1) × 27 = 1,296mm³
  Seg 2: (41+1) × 27 = 1,134mm³
  Seg 3: (35+1) × 27 = 972mm³
  Seg 4: (29+1) × 28 = 840mm³
  Total: 5,700mm³  (savings: 1,644mm³ × 7.99e-3 = 13.1g)
  Target: 88.19 − 13.1 ≈ 75.1g

Stress: each segment top at z=53 (same safe margin as v10).
  Root segment maintains same I as v10 → root stress ≈ 43 MPa ✓
  Step corners at bottom (compression fiber) → less critical than tension fiber.
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for ss-bracket-v14 (stepped tapered arm, target ~75g)."""
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

    arm_len  = 136.0                            # |136-150|=14 < 15mm load tol ✓
    fw       = 2.0
    t_wall   = min_wall                         # 0.5mm
    y_center = lp[1]                            # 50mm
    h_top    = 53.0                             # all segs top at z=53 — safe above load zone

    # Stepped tapered arm: 5 segments, bottom rises 6mm every 27mm of x
    # Root maintains z=0 for lower bolt connection; tip saves mass.
    segments = [
        (0.0,   27.0,  0.0),   # x_start, x_end, z_bottom → h=53
        (27.0,  54.0,  6.0),   # h=47
        (54.0,  81.0,  12.0),  # h=41
        (81.0,  108.0, 18.0),  # h=35
        (108.0, 136.0, 24.0),  # h=29; arm_len=136 ✓
    ]

    # Build arm from fused segments
    arm = None
    for x0, x1, z_bot in segments:
        z_top = h_top                           # always 53mm top

        outer = BRepPrimAPI_MakeBox(
            gp_Pnt(x0, y_center - fw / 2, z_bot),
            gp_Pnt(x1, y_center + fw / 2, z_top),
        ).Shape()

        # Inner void: leave solid walls (t_wall) on all sides
        # Bottom wall: z_bot to z_bot+t_wall (solid)
        # Top wall: z_top-t_wall to z_top (solid)
        # Left cap: only first seg (x0=0); void starts at x=plate_t
        x_void_start = plate_t if x0 == 0.0 else x0
        inner = BRepPrimAPI_MakeBox(
            gp_Pnt(x_void_start, y_center - fw / 2 + t_wall, z_bot + t_wall),
            gp_Pnt(x1,           y_center + fw / 2 - t_wall, z_top - t_wall),
        ).Shape()

        seg_shape = BRepAlgoAPI_Cut(outer, inner).Shape()

        if arm is None:
            arm = seg_shape
        else:
            arm = BRepAlgoAPI_Fuse(arm, seg_shape).Shape()

    # ── Mounting plate ───────────────────────────────────────────────────────────
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    body = BRepAlgoAPI_Fuse(arm, plate).Shape()

    # ── Bolt holes ───────────────────────────────────────────────────────────────
    for by, bz in bolt_pattern:
        ax = gp_Ax2(gp_Pnt(-1.0, by, bz), gp_Dir(1, 0, 0))
        cyl = BRepPrimAPI_MakeCylinder(ax, bolt_r, plate_t + 2.0).Shape()
        body = BRepAlgoAPI_Cut(body, cyl).Shape()

    # ── STEP export ──────────────────────────────────────────────────────────────
    writer = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
    writer.Transfer(body, STEPControl_AsIs)

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
        tmp = f.name
    try:
        writer.Write(tmp)
        return open(tmp, "rb").read()
    finally:
        os.unlink(tmp)
