"""
Metric-aware LLM agent — reads spec["scoring"]["metric"] and adapts strategy.

Three categories, three different bracket geometries:

  mass_grams      → minimize mass: thin walls, short arm, hollow ribs
  stiffness_to_weight → maximize ratio: efficient I-beam cross-section
  deflection_mm   → minimize tip deflection: fill the build volume, maximize area

The harness injects an LLMClient. You do not provide an API key.
"""

from __future__ import annotations

import json
import os
import tempfile

from build123d import (
    Box,
    BuildPart,
    Cylinder,
    Mode,
    Pos,
    export_step,
)

from forge.sdk.llm import LLMClient

# Geometry strategy descriptions sent to the LLM per metric
_STRATEGY = {
    "mass_grams": (
        "minimize total mass while still passing FEA. "
        "Use the shortest arm that reaches the load point. "
        "Use the thinnest walls allowed by min_wall_thickness_mm. "
        "Prefer a slim arm cross-section (small height and width)."
    ),
    "stiffness_to_weight": (
        "maximize stiffness-to-weight ratio (N / (mm * g)). "
        "Use an efficient I-beam or rectangular hollow cross-section for the arm — "
        "a tall, narrow arm resists bending with minimal material. "
        "Keep the arm just long enough to reach the load point. "
        "Balance arm_height vs arm_thickness: tall and thin beats short and wide."
    ),
    "deflection_mm": (
        "minimize tip deflection — maximize absolute stiffness regardless of mass. "
        "Fill as much of the build volume as possible. "
        "Use the full available arm height and width. "
        "A solid, wide arm cross-section is better than a thin one. "
        "Mass does not matter; stiffness does."
    ),
}


def generate(spec: dict, llm: LLMClient) -> bytes:
    c = spec["constraints"]
    scoring = spec["scoring"]
    metric = scoring["metric"]          # "mass_grams" | "stiffness_to_weight" | "deflection_mm"
    direction = scoring["direction"]    # "minimize" | "maximize"

    bv = c["build_volume_mm"]           # [x, y, z]
    load_pt = c["load_point_mm"]        # [x, y, z]
    bolt_d = c["bolt_diameter_clearance_mm"]
    min_wall = c["min_wall_thickness_mm"]
    bolt_pattern = c["bolt_pattern_mm"]  # [[y, z], ...]

    strategy = _STRATEGY.get(metric, _STRATEGY["mass_grams"])

    prompt = f"""You are a structural CAD assistant optimizing a cantilever bracket.

Objective: {direction} {metric}
Strategy: {strategy}

Spec:
  build_volume_mm: {bv}  (x=arm direction, y=width, z=height)
  load_point_mm: {load_pt}
  bolt_clearance_mm: {bolt_d}
  min_wall_mm: {min_wall}

Geometry: vertical mount plate (at x=0) + horizontal arm (extends along +x).

Reply with ONLY valid JSON, no prose, using exactly these keys:
  arm_length      — arm length along x-axis (int, must reach x={int(load_pt[0]) + 5})
  arm_height      — arm cross-section height along z (int, >= {max(6, int(min_wall) + 4)})
  arm_width       — arm cross-section width along y (int, >= {max(6, int(min_wall) + 4)})
  plate_height    — mount plate height along z (int, <= {int(bv[2])})
  plate_width     — mount plate width along y (int, <= {int(bv[1])})
  plate_thickness — mount plate thickness along x (int, >= {max(5, int(min_wall) + 3)})
"""

    raw = llm.chat([{"role": "user", "content": prompt}], max_tokens=256)
    dims = json.loads(raw)

    arm_len = max(int(load_pt[0]) + 5, int(dims["arm_length"]))
    arm_h   = int(dims["arm_height"])
    arm_w   = int(dims["arm_width"])
    plate_h = int(dims["plate_height"])
    plate_w = int(dims["plate_width"])
    plate_t = int(dims["plate_thickness"])

    # Clamp to build volume
    arm_len = min(arm_len, int(bv[0]) - plate_t)
    arm_h   = min(arm_h, int(bv[2]))
    arm_w   = min(arm_w, int(bv[1]))
    plate_h = min(plate_h, int(bv[2]))
    plate_w = min(plate_w, int(bv[1]))

    with BuildPart() as part:
        # Vertical mount plate
        with Pos(plate_t / 2, plate_w / 2, plate_h / 2):
            Box(plate_t, plate_w, plate_h)

        # Horizontal arm — centered on mount plate, extends along +x
        arm_y = plate_w / 2
        arm_z = arm_h / 2
        arm_cx = plate_t + arm_len / 2
        with Pos(arm_cx, arm_y, arm_z):
            Box(arm_len, arm_w, arm_h)

        # Bolt holes through mount plate (bolt_pattern = [[y, z], ...])
        bolt_r = bolt_d / 2
        for by, bz in bolt_pattern:
            with Pos(plate_t / 2, by, bz):
                Cylinder(bolt_r, plate_t + 2, mode=Mode.SUBTRACT, rotation=(0, 90, 0))

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
        path = f.name
    try:
        export_step(part.part, path)
        return open(path, "rb").read()
    finally:
        os.unlink(path)
