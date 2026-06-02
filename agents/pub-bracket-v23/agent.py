"""
pub-bracket-v23: Hollow-box arm + frame plate for pub_004_medium.

Improvement over v22: adds grid frame plate (single interior void),
cutting ~2.9g of unused plate material.

Design:
  - Arm: hollow box, aw = 3×mw = 3.6mm, inner cavity ends at al-mw (solid tip)
    - al = lx − 12mm = 71.3mm
    - h = min(bvz−5, max(bvz×0.75, lz+15+mw)) ≈ 70.4mm
  - Frame plate: 1.2mm thick, # grid with mw-wide cross-ribs at bolt-gap midpoints.
    4 windows each ~22.5×22.5mm (single large void 46.2×46.2mm caused 92.7 MPa).
    Arm (yc=37.5, aw=3.6mm) spans through right-column windows; Fuse restores arm spine.

Analytical check (PLA, 25 MPa allowable):
  h ≈ 70.4 mm, al = 71.3 mm, arm cross-section 171.8 mm²
  M = 303.22 × 71.3 = 21,620 N·mm, c = 35.2 mm, I ≈ 70,700 mm⁴
  σ ≈ 10.8 MPa → 43% utilisation ✓

Estimated mass ≈ 18.1 g (−14% vs v22 at 21.02 g).
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for pub-bracket-v23 (hollow arm + frame plate, pub_004)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c   = spec["constraints"]
    bp  = c["bolt_pattern_mm"]
    bd  = c["bolt_diameter_clearance_mm"]
    lp  = c["load_point_mm"]
    mw  = c.get("min_wall_thickness_mm", 1.2)
    bv  = c["build_volume_mm"]

    lx, ly, lz = lp
    r  = bd / 2.0
    mg = r + mw

    # Plate extents
    pt    = mw
    py0_r = min(p[0] for p in bp) - mg
    py1_r = max(p[0] for p in bp) + mg
    pz0_r = min(p[1] for p in bp) - mg
    pz1_r = max(p[1] for p in bp) + mg

    dy = py1_r - py0_r
    if dy > bv[1] - 0.5:
        sh = (dy - (bv[1] - 0.5)) / 2.0
        py0, py1 = py0_r + sh, py1_r - sh
    else:
        py0, py1 = py0_r, py1_r

    dz = pz1_r - pz0_r
    if dz > bv[2] - 0.5:
        sh = (dz - (bv[2] - 0.5)) / 2.0
        pz0, pz1 = pz0_r + sh, pz1_r - sh
    else:
        pz0, pz1 = pz0_r, pz1_r

    # Hollow arm (same as v22)
    aw = 3.0 * mw

    h_need = lz + 15.0 + mw
    h_want = bv[2] * 0.75
    h      = min(bv[2] - 5.0, max(h_want, h_need))

    al = lx - 12.0
    al = min(al, bv[0] - 2.0)

    yc = ly

    outer = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, yc - aw / 2, 0.0),
        gp_Pnt(al,  yc + aw / 2, h),
    ).Shape()

    # Inner cavity ends at al-mw so the tip is inherently solid (no Fuse needed)
    inner = BRepPrimAPI_MakeBox(
        gp_Pnt(pt,      yc - aw / 2 + mw, mw),
        gp_Pnt(al - mw, yc + aw / 2 - mw, h - mw),
    ).Shape()

    arm = BRepAlgoAPI_Cut(outer, inner).Shape()

    # Frame plate: solid plate with interior void cut out
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, py0, pz0),
        gp_Pnt(pt,  py1, pz1),
    ).Shape()

    # Frame plate: cut interior voids using a # (hash) cross-rib pattern.
    # For each bolt-gap rectangle, subdivide with mw-wide ribs at the midpoints
    # to create 4 smaller windows. This prevents the stress concentration that
    # a single large void (46.2×46.2mm) caused for the 2×2 bolt grid (92.7 MPa).
    by_cols = sorted(set(p[0] for p in bp))
    bz_rows = sorted(set(p[1] for p in bp))

    for i in range(len(by_cols) - 1):
        for j in range(len(bz_rows) - 1):
            vy0 = by_cols[i]     + mg
            vy1 = by_cols[i + 1] - mg
            vz0 = bz_rows[j]     + mg
            vz1 = bz_rows[j + 1] - mg
            if vy0 >= vy1 or vz0 >= vz1:
                continue
            # Midpoint ribs (mw wide) subdivide gap into 4 sub-windows.
            vy_mid = (vy0 + vy1) / 2.0
            vz_mid = (vz0 + vz1) / 2.0
            sub_voids = [
                (vy0,          vy_mid - mw / 2, vz0,          vz_mid - mw / 2),
                (vy_mid + mw / 2, vy1,          vz0,          vz_mid - mw / 2),
                (vy0,          vy_mid - mw / 2, vz_mid + mw / 2, vz1),
                (vy_mid + mw / 2, vy1,          vz_mid + mw / 2, vz1),
            ]
            for sv_y0, sv_y1, sv_z0, sv_z1 in sub_voids:
                if sv_y0 < sv_y1 and sv_z0 < sv_z1:
                    void = BRepPrimAPI_MakeBox(
                        gp_Pnt(0.0, sv_y0, sv_z0),
                        gp_Pnt(pt,  sv_y1, sv_z1),
                    ).Shape()
                    plate = BRepAlgoAPI_Cut(plate, void).Shape()

    body = BRepAlgoAPI_Fuse(arm, plate).Shape()

    for by, bz in bp:
        ax  = gp_Ax2(gp_Pnt(-1.0, by, bz), gp_Dir(1, 0, 0))
        cyl = BRepPrimAPI_MakeCylinder(ax, r, pt + 2.0).Shape()
        body = BRepAlgoAPI_Cut(body, cyl).Shape()

    writer = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
    writer.Transfer(body, STEPControl_AsIs)

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as tf:
        tmp = tf.name
    try:
        writer.Write(tmp)
        return open(tmp, "rb").read()
    finally:
        os.unlink(tmp)
