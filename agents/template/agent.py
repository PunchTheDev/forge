"""
Template agent — start here.

Contract: implement generate(spec) -> bytes (STEP file).

The eval harness calls generate() with the spec dict for each problem.
Return valid STEP bytes. The harness handles geometry checks and FEA;
your job is to return the lightest part that passes all constraints.

See QUICKSTART.md for a full walkthrough.
"""

from __future__ import annotations

# TODO: import your geometry library
# from build123d import ...          # recommended
# from OCP.BRepPrimAPI import ...    # raw OCP (see agents/baseline/)


def generate(spec: dict) -> bytes:
    """
    Build and return a STEP file for the given spec.

    Args:
        spec: Problem specification dict. Key structure:
            spec["constraints"]["load_n"]               — applied load in Newtons
            spec["constraints"]["load_point_mm"]        — [x, y, z] load application point
            spec["constraints"]["build_volume_mm"]      — [x, y, z] max bounding box
            spec["constraints"]["bolt_pattern_mm"]      — [[y, z], ...] bolt hole centers (x=0 plane)
            spec["constraints"]["bolt_diameter_clearance_mm"] — minimum clearance diameter
            spec["constraints"]["min_wall_thickness_mm"] — minimum feature wall
            spec["constraints"]["max_overhang_deg"]     — max overhang from vertical
            spec["material"]                            — material name (see benchmark/materials.py)
            spec["safety_factor"]                       — FEA stress safety factor

    Returns:
        STEP file as raw bytes. Must be valid AP203 STEP.

    Notes:
        - Must be deterministic: same spec → same bytes every call.
          If you use any randomness, fix the seed (e.g. random.seed(42)).
        - The FEA mesh uses C3D4 linear tets at ~2 mm characteristic length.
          Avoid features thinner than 3 mm — they produce degenerate elements.
        - Lower mass = better score. There is no ceiling; keep optimizing.
    """

    constraints = spec["constraints"]

    # TODO: read the constraints you need
    # load_n = constraints["load_n"]
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
    """Convert an OCP TopoDS_Shape to STEP AP203 bytes."""
    import os
    import tempfile

    from OCP.Interface import Interface_Static
    from OCP.STEPControl import STEPControl_AsIs, STEPControl_Writer

    writer = STEPControl_Writer()
    Interface_Static.SetCVal_s("write.step.schema", "AP203")
    writer.Transfer(shape, STEPControl_AsIs)

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
        path = f.name
    try:
        writer.Write(path)
        with open(path, "rb") as f:
            return f.read()
    finally:
        os.unlink(path)
