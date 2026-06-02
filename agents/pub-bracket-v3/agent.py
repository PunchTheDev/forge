"""
pub-bracket-v3: Parametric hollow-box cantilever bracket for pub_003_medium.

Target: PETG (FDM), 53 kg load at ~110 mm arm.
Design: thick-walled hollow box arm with full-height mounting plate.
  - Arm spans z=0 to 75% of build volume z (maximises second moment of area)
  - Arm is centred on the load y-coordinate
  - Arm reaches to within 15 mm of the load x-coordinate
  - Plate: minimal rectangle enclosing bolt holes + clearance, clipped to bv
"""

from __future__ import annotations

import os
import tempfile


def generate(spec: dict) -> bytes:
    """Return STEP bytes for a PETG hollow-box cantilever bracket."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder
    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    c = spec["constraints"]
    bolts    = c["bolt_pattern_mm"]
    bolt_d   = c["bolt_diameter_clearance_mm"]
    lp       = c["load_point_mm"]
    t        = c.get("min_wall_thickness_mm", 1.2)
    bv       = c["build_volume_mm"]

    lx, ly, lz = lp
    bvx, bvy, bvz = bv

    rad = bolt_d / 2.0
    gap = rad + t   # margin between bolt edge and part edge

    # Mounting plate extents
    pt    = t                                         # plate thickness (x-dir)
    py0_r = min(b[0] for b in bolts) - gap
    py1_r = max(b[0] for b in bolts) + gap
    pz0_r = min(b[1] for b in bolts) - gap
    pz1_r = max(b[1] for b in bolts) + gap

    ys = py1_r - py0_r
    if ys > bvy - 0.5:
        d = (ys - (bvy - 0.5)) / 2.0
        py0, py1 = py0_r + d, py1_r - d
    else:
        py0, py1 = py0_r, py1_r

    zs = pz1_r - pz0_r
    if zs > bvz - 0.5:
        d = (zs - (bvz - 0.5)) / 2.0
        pz0, pz1 = pz0_r + d, pz1_r - d
    else:
        pz0, pz1 = pz0_r, pz1_r

    # Hollow arm: 3t wide, tall enough for load clearance
    w       = 3.0 * t                              # arm width (y-direction)
    h_floor = lz + 15.0 + t                       # arm top must clear load zone
    h_tgt   = bvz * 0.75                          # target: 75% of z volume
    h       = min(bvz - 5.0, max(h_tgt, h_floor))

    # Arm length: reach to ~15 mm from load point
    length = min(max(lx - 15.0, lx * 0.85), bvx - 2.0)

    yc = ly   # arm centred on load y

    # Outer box
    outer_box = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0,    yc - w / 2, 0.0),
        gp_Pnt(length, yc + w / 2, h),
    ).Shape()

    # Interior void (open on the +x end, walled on all other faces)
    inner_void = BRepPrimAPI_MakeBox(
        gp_Pnt(pt,     yc - w / 2 + t, t),
        gp_Pnt(length, yc + w / 2 - t, h - t),
    ).Shape()

    arm = BRepAlgoAPI_Cut(outer_box, inner_void).Shape()

    # Mounting plate
    plate = BRepPrimAPI_MakeBox(
        gp_Pnt(0.0, py0, pz0),
        gp_Pnt(pt,  py1, pz1),
    ).Shape()

    body = BRepAlgoAPI_Fuse(arm, plate).Shape()

    # Bolt clearance holes
    for by, bz in bolts:
        ax  = gp_Ax2(gp_Pnt(-1.0, by, bz), gp_Dir(1, 0, 0))
        cyl = BRepPrimAPI_MakeCylinder(ax, rad, pt + 2.0).Shape()
        body = BRepAlgoAPI_Cut(body, cyl).Shape()

    # Write STEP
    writer = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP214IS")
    writer.Transfer(body, STEPControl_AsIs)

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
        path = f.name
    try:
        writer.Write(path)
        return open(path, "rb").read()
    finally:
        os.unlink(path)
