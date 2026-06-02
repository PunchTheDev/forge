"""
Example LLM agent — observe → plan → act.

The harness injects an LLMClient bound to a whitelisted model. This agent
asks the LLM to propose dimensions for a simple L-bracket, then builds it
with build123d and returns STEP bytes.
"""

from __future__ import annotations

import json

from build123d import (
    Box,
    BuildPart,
    Cylinder,
    Location,
    Mode,
    Pos,
    export_step,
)

from forge.sdk.llm import LLMClient


def generate(spec: dict, llm: LLMClient) -> bytes:
    # ── Observe ──────────────────────────────────────────────────────────────
    c = spec["constraints"]
    bv = c["build_volume_mm"]          # [x, y, z] bounding box
    load_pt = c["load_point_mm"]       # [x, y, z]
    bolt_d = c["bolt_diameter_clearance_mm"]
    min_wall = c["min_wall_thickness_mm"]

    # ── Plan (LLM proposes dimensions) ────────────────────────────────────────
    prompt = f"""You are a mechanical CAD assistant. Given this bracket spec, propose
integer dimensions (mm) for a minimal L-bracket with a vertical mount plate and a
horizontal arm. Reply with ONLY valid JSON, no prose.

Spec:
  build_volume_mm: {bv}
  load_point_mm: {load_pt}
  bolt_clearance_mm: {bolt_d}
  min_wall_mm: {min_wall}

Return JSON with exactly these keys:
  arm_length   — horizontal arm length (x-axis), int
  arm_thickness — arm wall thickness, int >= {max(4, int(min_wall) + 2)}
  plate_height  — mount plate height (z-axis), int
  plate_width   — mount plate width (y-axis), int
  plate_thickness — mount plate thickness (x-axis), int >= {max(4, int(min_wall) + 2)}
"""

    raw = llm.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=256,
    )

    dims = json.loads(raw)
    arm_len   = int(dims["arm_length"])
    arm_t     = int(dims["arm_thickness"])
    plate_h   = int(dims["plate_height"])
    plate_w   = int(dims["plate_width"])
    plate_t   = int(dims["plate_thickness"])

    # Clamp to build volume
    arm_len = min(arm_len, int(bv[0]) - plate_t)
    plate_h = min(plate_h, int(bv[2]))
    plate_w = min(plate_w, int(bv[1]))

    # ── Act (build geometry) ──────────────────────────────────────────────────
    with BuildPart() as part:
        # Vertical mount plate at x=0 face
        with Pos(plate_t / 2, plate_w / 2, plate_h / 2):
            Box(plate_t, plate_w, plate_h)

        # Horizontal arm extending along +x
        arm_cx = plate_t + arm_len / 2
        with Pos(arm_cx, plate_w / 2, arm_t / 2):
            Box(arm_len, plate_w, arm_t)

        # Clear bolt holes through the mount plate
        bolt_r = bolt_d / 2
        for (by, bz) in c["bolt_pattern_mm"]:
            with Pos(0, by + plate_w / 2 - plate_w / 2, bz):
                # Cylinder along x-axis
                Cylinder(bolt_r, plate_t, mode=Mode.SUBTRACT,
                         rotation=(0, 90, 0))

    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
        path = f.name
    try:
        export_step(part.part, path)
        return open(path, "rb").read()
    finally:
        os.unlink(path)
