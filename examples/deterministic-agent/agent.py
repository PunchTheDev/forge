"""
Deterministic agent — no LLM, pure geometric rules.

Three metric-specific strategies:

  mass_grams          → minimal L-bracket: thinnest walls, shortest arm
  stiffness_to_weight → tall narrow arm: maximizes second moment of area / mass
  deflection_mm       → bulk solid arm: fills build volume for maximum stiffness

No LLMClient is used. The harness still injects `llm` but this agent ignores it.
The `generate` signature must accept it regardless.
"""

from __future__ import annotations

import math
import os
import tempfile

from build123d import Box, BuildPart, Cylinder, Mode, Pos, export_step

from forge.sdk.llm import LLMClient


def generate(spec: dict, llm: LLMClient) -> bytes:
    c = spec["constraints"]
    metric = spec["scoring"]["metric"]

    bv = c["build_volume_mm"]           # [x, y, z] hard limits
    load_pt = c["load_point_mm"]        # [x, y, z] — arm must reach x
    bolt_d = c["bolt_diameter_clearance_mm"]
    min_wall = c["min_wall_thickness_mm"]
    bolts = c["bolt_pattern_mm"]        # [[y, z], ...]

    # Mount plate must enclose all bolt centers with a clearance ring.
    # Bolt coordinates are non-negative offsets from the mount face corner.
    bolt_r = bolt_d / 2
    edge_margin = bolt_r + max(min_wall, 2.0)

    # Minimum plate extent (from 0) to cover all bolts
    plate_w = min(max(b[0] for b in bolts) + edge_margin, bv[1])
    plate_h = min(max(b[1] for b in bolts) + edge_margin, bv[2])
    plate_w = max(plate_w, min_wall * 4)
    plate_h = max(plate_h, min_wall * 4)

    if metric == "mass_grams":
        dims = _mass_dims(bv, load_pt, min_wall, plate_w, plate_h)
    elif metric == "stiffness_to_weight":
        dims = _stiffness_dims(bv, load_pt, min_wall, plate_w, plate_h)
    else:  # deflection_mm
        dims = _deflection_dims(bv, load_pt, min_wall, plate_w, plate_h)

    plate_t = dims["plate_t"]
    arm_len = dims["arm_len"]
    arm_h = dims["arm_h"]
    arm_w = dims["arm_w"]

    with BuildPart() as part:
        # Vertical mount plate — starts at (0, 0, 0), plate_w × plate_h face
        with Pos(plate_t / 2, plate_w / 2, plate_h / 2):
            Box(plate_t, plate_w, plate_h)

        # Horizontal arm — centered in y with plate, sits at base of z, extends +x
        arm_cx = plate_t + arm_len / 2
        arm_cy = plate_w / 2
        arm_cz = arm_h / 2
        with Pos(arm_cx, arm_cy, arm_cz):
            Box(arm_len, arm_w, arm_h)

        # Clear bolt holes through mount plate
        for by, bz in bolts:
            with Pos(plate_t / 2, by, bz):
                Cylinder(bolt_r, plate_t + 2, mode=Mode.SUBTRACT, rotation=(0, 90, 0))

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
        path = f.name
    try:
        export_step(part.part, path)
        return open(path, "rb").read()
    finally:
        os.unlink(path)


def _mass_dims(bv, load_pt, min_wall, plate_w, plate_h) -> dict:
    """Minimize mass: thinnest walls, shortest arm that clears load point."""
    wall = max(min_wall, 2.0)
    plate_t = wall * 2
    arm_len = math.ceil(load_pt[0]) + 5       # reach load point + small margin
    arm_len = min(arm_len, int(bv[0]) - int(plate_t))
    arm_h = wall * 3                           # thin cross-section
    arm_w = min(plate_w * 0.4, wall * 5)
    return dict(plate_t=plate_t, arm_len=arm_len, arm_h=arm_h, arm_w=arm_w)


def _stiffness_dims(bv, load_pt, min_wall, plate_w, plate_h) -> dict:
    """Maximize stiffness-to-weight: tall narrow arm (I-beam principle).

    Bending stiffness scales as h^3 * w; mass scales as h * w.
    So stiffness/mass ~ h^2: tall beats wide.
    """
    wall = max(min_wall, 2.0)
    plate_t = wall * 3
    arm_len = math.ceil(load_pt[0]) + 5
    arm_len = min(arm_len, int(bv[0]) - int(plate_t))
    arm_h = int(bv[2] * 0.8)                  # tall — h^2 gain
    arm_w = max(wall * 3, int(plate_w * 0.25))  # narrow — keep mass low
    return dict(plate_t=plate_t, arm_len=arm_len, arm_h=arm_h, arm_w=arm_w)


def _deflection_dims(bv, load_pt, min_wall, plate_w, plate_h) -> dict:
    """Minimize deflection: fill build volume — max cross-section wins."""
    plate_t = int(bv[0] * 0.12)               # thick plate for rigidity
    arm_len = int(bv[0]) - plate_t
    arm_h = int(bv[2])                         # full height
    arm_w = int(bv[1])                         # full width
    return dict(plate_t=plate_t, arm_len=arm_len, arm_h=arm_h, arm_w=arm_w)
