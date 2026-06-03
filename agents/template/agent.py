"""
Template agent — start here.

Required signature:

    generate(spec: dict, llm: LLMClient) -> bytes

The harness injects LLMClient automatically — no API key required.
Agents without the `llm` parameter are rejected at eval time.

See QUICKSTART.md for a full walkthrough. For a recommended starting point
that adapts to all three competition categories, see examples/metric-aware-agent/.
"""

from __future__ import annotations

from forge.sdk.llm import LLMClient

# TODO: import your geometry library
# from build123d import ...          # recommended
# from OCP.BRepPrimAPI import ...    # raw OCP (see agents/baseline/)


def generate(spec: dict, llm: LLMClient) -> bytes:
    """
    Build and return a STEP file for the given spec.

    Use `llm.chat(messages)` to call the whitelisted LLM
    (claude-haiku-4-5, claude-3-5-haiku, or gpt-4o-mini).

    Args:
        spec: Problem specification dict. Key fields:
            spec["constraints"]["load_newtons"]               — load in Newtons
            spec["constraints"]["load_point_mm"]              — [x, y, z] load point
            spec["constraints"]["build_volume_mm"]            — [x, y, z] bounding box
            spec["constraints"]["bolt_pattern_mm"]            — [[y, z], ...] bolt centers
            spec["constraints"]["bolt_diameter_clearance_mm"] — hole clearance
            spec["constraints"]["min_wall_thickness_mm"]      — minimum wall
            spec["constraints"]["max_overhang_deg"]           — max printable overhang
            spec["constraints"]["safety_factor"]              — FEA stress safety factor
            spec["material"]                                  — material name
            spec["scoring"]["metric"]                         — "mass_grams" | "stiffness_to_weight" | "deflection_mm"

    Returns:
        STEP file as raw bytes (AP214IS schema required).

    Notes:
        - Must be deterministic: same spec → same bytes. Fix any random seeds.
        - Avoid features thinner than 3 mm — they produce degenerate FEA elements.
    """

    constraints = spec["constraints"]
    metric = spec["scoring"]["metric"]  # "mass_grams" | "stiffness_to_weight" | "deflection_mm"

    # TODO: use the LLM to reason about geometry parameters
    # response = llm.chat([
    #     {"role": "system", "content": "You are a structural engineering assistant."},
    #     {"role": "user", "content": f"Suggest wall thickness (mm) for a bracket optimizing {metric}. "
    #                                 f"Load: {constraints['load_newtons']} N. Reply with a single number."},
    # ])
    # thickness_mm = float(response.strip())

    # TODO: read the constraints you need
    # load_n = constraints["load_newtons"]
    # load_point = constraints["load_point_mm"]      # [x, y, z]
    # build_vol = constraints["build_volume_mm"]     # [x, y, z] max box
    # bolt_pattern = constraints["bolt_pattern_mm"]  # [[y, z], ...]
    # bolt_d = constraints["bolt_diameter_clearance_mm"]

    # TODO: build your geometry using the parameters above
    # shape = ...

    # TODO: write to STEP and return bytes
    # return _to_step_bytes(shape)

    raise NotImplementedError(
        "Replace this with your geometry. See examples/metric-aware-agent/ for a working example."
    )


# ---------------------------------------------------------------------------
# Helper: write an OCP shape to STEP bytes
# ---------------------------------------------------------------------------

def _to_step_bytes(shape) -> bytes:
    """Convert an OCP TopoDS_Shape to STEP AP214IS bytes."""
    import os
    import tempfile

    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

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
