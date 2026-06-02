"""
Aluminum bracket for spec 002_equipment_mount (Al6061-T6, 100kg, 120mm arm).

Failure history:
  PRs #40-43: h_root=80, h_tip=50 → arm 34.25mm above plate → junction stress 163.7 MPa
  PR #48 v1:  h_root=45, h_tip=15 → arm top at x=120mm = 16mm → load gap=29mm > 15mm tol
  PR #48 v2:  h_root=50, h_tip=32 → arm extends 4.25mm above plate → junction stress 112.3 MPa
                                     (allowable 110.4 MPa) — junction stress + 3x higher moment

Fix (v3):
  h_root = 43mm  → arm top flange z=[40.5,43mm], plate_z1=45.75mm → arm FULLY within plate
                    no junction stress concentration (like spec-001's fully-supported arm) ✓
  h_tip  = 31mm  → arm top at x=120mm = 31.4mm; gap to load z=45mm = 13.6mm < 15mm tol ✓
  flange_w=10mm  → bolt at (y=40,z=0) hole edge at y=44.25mm;
                    flange_w=12mm: arm starts at y=44mm (0.25mm overlap with bolt hole!)
                    flange_w=10mm: arm starts at y=45mm (0.75mm clearance) ✓

Taper: 43/31 = 1.39:1 (mild, mesh-stable)

Load node check:
  h(x=120) = 43 - (43-31)*120/124 = 43 - 11.6 = 31.4mm
  |31.4 - lp_z=45| = 13.6mm < tol=15mm ✓

Section modulus at arm root (h_root=43mm, flange_w=10mm, flange_t=2.5mm, web_w=2mm):
  M         = 981 × 120 = 117,720 N·mm
  c         = 21.5mm
  I_web     = 2 × (38)^3/12 = 9,162 mm4
  I_flange  = 2 × 10 × 2.5 × (21.5-1.25)^2 = 20,494 mm4
  I_total   = 29,656 mm4
  sigma     = 117,720 × 21.5 / 29,656 = 85.3 MPa  (77.3% of 110.4 MPa ✓)

Mass estimate (Al density 2.71e-3 g/mm3):
  Web avg h: (38+26)/2=32mm → 124×2×32=7,936 mm3 → 21.5g
  Flanges:   2×124×10×2.5  = 6,200 mm3 → 16.8g
  Plate solid: 3×91.5×51.5 = 14,147 mm3 → 38.3g
  6 bolt holes: -1,021 mm3 → -2.8g
  Pockets (1.8mm deep):
    Left  (y: 6.25→43mm, z: 6.25→33.75mm): 1.8×36.75×27.5=1,818mm3 → -4.9g
    Right (y: 57→73.75mm, z: 6.25→33.75mm): 1.8×16.75×27.5=829mm3 → -2.2g
  Total = 66.7g   (vs 380g baseline, -82.4%)
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for an aluminum 6061 equipment mount bracket."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolt_pattern = c["bolt_pattern_mm"]
    bolt_d = c["bolt_diameter_clearance_mm"]   # 8.5mm → bolt_r=4.25mm
    lp = c["load_point_mm"]                    # [120, 50, 45]

    by_coords = [p[0] for p in bolt_pattern]
    bz_coords = [p[1] for p in bolt_pattern]
    bolt_r = bolt_d / 2.0
    margin = bolt_r + 1.5                       # 5.75mm structural ring

    plate_t  = 3.0
    plate_y0 = min(by_coords) - margin
    plate_y1 = max(by_coords) + margin
    plate_z0 = min(bz_coords) - margin
    plate_z1 = max(bz_coords) + margin          # 45.75mm

    arm_len  = lp[0] + 4.0                     # 124mm

    web_w    = 2.0
    flange_w = 10.0   # 10mm: arm edge at y=45mm, 0.75mm clear of bolt at y=40 (hole r=4.25)
    flange_t = 2.5
    h_root   = 43.0   # arm fully within plate: top at z=43mm < plate_z1=45.75mm → no junction
    h_tip    = 31.0   # arm top at x=120mm = 31.4mm; gap to load z=45mm = 13.6mm < 15mm tol
    y_center = lp[1]  # 50mm

    # ── Arm ───────────────────────────────────────────────────────────────────
    bot_flange = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, y_center - flange_w / 2, 0.0),
        gp_Pnt(arm_len, y_center + flange_w / 2, flange_t),
    ).Shape()

    web = _loft_rect(
        x0=0.0, x1=arm_len,
        y0=y_center - web_w / 2, y1=y_center + web_w / 2,
        z0_near=flange_t, z1_near=h_root - flange_t,
        z0_far=flange_t,  z1_far=h_tip - flange_t,
    )

    top_flange = _loft_rect(
        x0=0.0, x1=arm_len,
        y0=y_center - flange_w / 2, y1=y_center + flange_w / 2,
        z0_near=h_root - flange_t, z1_near=h_root,
        z0_far=h_tip - flange_t,   z1_far=h_tip,
    )

    fuse1 = BRepAlgoAPI_Fuse(bot_flange, web)
    fuse1.Build()
    fuse2 = BRepAlgoAPI_Fuse(fuse1.Shape(), top_flange)
    fuse2.Build()

    # ── Mounting plate ────────────────────────────────────────────────────────
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, plate_y0, plate_z0),
        gp_Pnt(plate_t, plate_y1, plate_z1),
    ).Shape()

    fuse3 = BRepAlgoAPI_Fuse(fuse2.Shape(), plate)
    fuse3.Build()
    shape = fuse3.Shape()

    # ── Bolt holes ────────────────────────────────────────────────────────────
    for bby, bbz in bolt_pattern:
        axis = gp_Ax2(gp_Pnt(-1.0, bby, bbz), gp_Dir(1.0, 0.0, 0.0))
        hole = BRepPrimAPI_MakeCylinder(axis, bolt_r, plate_t + 2.0).Shape()
        cut_op = BRepAlgoAPI_Cut(shape, hole)
        cut_op.Build()
        shape = cut_op.Shape()

    # ── Wall-face pockets: 1.8mm deep (1.2mm remaining > 0.8mm min-wall) ─────
    pocket_depth = 1.8

    bolt_clear = bolt_r + 2.0                   # 6.25mm buffer
    arm_buf    = 2.0

    arm_y_min = y_center - flange_w / 2         # 45mm
    arm_y_max = y_center + flange_w / 2         # 55mm

    pkt_z0 = min(bz_coords) + bolt_clear        # 6.25mm
    pkt_z1 = max(bz_coords) - bolt_clear        # 33.75mm

    # Left pocket (y: 6.25 → 43mm)
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

    # Right pocket (y: 57 → 73.75mm)
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


def _loft_rect(
    x0: float, x1: float,
    y0: float, y1: float,
    z0_near: float, z1_near: float,
    z0_far: float, z1_far: float,
):
    """Loft a solid between two axis-aligned rectangles at x=x0 and x=x1."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
    from OCP.gp import gp_Pnt

    def make_rect_wire(x, ya, yb, za, zb):
        pts = [
            gp_Pnt(x, ya, za), gp_Pnt(x, yb, za),
            gp_Pnt(x, yb, zb), gp_Pnt(x, ya, zb),
        ]
        wire = BRepBuilderAPI_MakeWire()
        for i in range(4):
            e = BRepBuilderAPI_MakeEdge(pts[i], pts[(i + 1) % 4]).Edge()
            wire.Add(e)
        return wire.Wire()

    loft = BRepOffsetAPI_ThruSections(True)
    loft.AddWire(make_rect_wire(x0, y0, y1, z0_near, z1_near))
    loft.AddWire(make_rect_wire(x1, y0, y1, z0_far, z1_far))
    loft.Build()
    return loft.Shape()
