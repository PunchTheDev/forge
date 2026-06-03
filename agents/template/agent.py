"""
Template agent — start here.

Two supported signatures:

    generate(spec: dict) -> bytes              # static agent
    generate(spec: dict, llm: LLMClient) -> bytes  # LLM agent (recommended)

The harness detects which you use via inspect.signature and injects LLMClient
automatically if present — no API key required from you.

See QUICKSTART.md for a full walkthrough and examples/llm-agent/ for an
LLM agent example.
"""

from __future__ import annotations

# To use the LLM client, uncomment:
# from forge.sdk.llm import LLMClient

# TODO: import your geometry library
# from build123d import ...          # recommended
# from OCP.BRepPrimAPI import ...    # raw OCP (see agents/baseline/)


def generate(spec: dict) -> bytes:
    """
    Build and return a STEP file for the given spec.

    To use an LLM, change the signature to: generate(spec, llm: LLMClient)

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

    # TODO: read the constraints you need
    # load_n = constraints["load_newtons"]
    # load_point = constraints["load_point_mm"]      # [x, y, z]
    # build_vol = constraints["build_volume_mm"]     # [x, y, z] max box
    # bolt_pattern = constraints["bolt_pattern_mm"]  # [[y, z], ...]
    # bolt_d = constraints["bolt_diameter_clearance_mm"]

    # TODO: build your geometry
    # shape = ...

    # TODO: write to STEP and return bytes
    # return _to_step_bytes(shape)

    raise NotImplementedError(
        "Replace this with your geometry. See QUICKSTART.md for examples."
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
