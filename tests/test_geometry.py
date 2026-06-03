"""
Unit tests for benchmark/geometry.py.

Tests use OCC primitive shapes (box, thin plate) constructed in-process so
no external STEP file is needed for fixtures.  All tests that require OCP
are skipped automatically when the library is not installed.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

# Probe for OCP availability once at module load time.
GEOMETRY_AVAILABLE = False
try:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    GEOMETRY_AVAILABLE = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_step_bytes(shape) -> bytes:
    """Serialise an OCC shape to STEP bytes."""
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCP.IFSelect import IFSelect_RetDone

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
        path = f.name
    try:
        writer = STEPControl_Writer()
        writer.Transfer(shape, STEPControl_AsIs)
        status = writer.Write(path)
        if status != IFSelect_RetDone:
            raise RuntimeError("STEP write failed")
        return Path(path).read_bytes()
    finally:
        os.unlink(path)


def _box(x: float, y: float, z: float):
    """Return an OCC solid box with given dimensions."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    return BRepPrimAPI_MakeBox(x, y, z).Shape()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mat_pla():
    from benchmark.materials import get
    return get("pla")


@pytest.fixture
def spec_base():
    """A generic spec that gives sensible defaults for geometry tests."""
    return {
        "constraints": {
            "load_newtons": 100.0,
            "load_point_mm": [50.0, 25.0, 25.0],
            "safety_factor": 1.5,
            "bolt_pattern_mm": [
                [0.0, 0.0],
                [50.0, 0.0],
                [0.0, 50.0],
                [50.0, 50.0],
            ],
            "bolt_diameter_clearance_mm": 6.5,
            "mount_face_x_mm": 0.0,
            "build_volume_mm": [100.0, 80.0, 80.0],
            "max_overhang_deg": 45.0,
            "min_wall_thickness_mm": 1.2,
        },
        "scoring": {"metric": "mass_grams", "direction": "minimize"},
    }


# ---------------------------------------------------------------------------
# Build-volume checks
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not GEOMETRY_AVAILABLE, reason="OCP not installed")
class TestBuildVolume:
    def test_fits_passes(self, spec_base, mat_pla):
        from benchmark.geometry import validate

        step = _make_step_bytes(_box(80.0, 60.0, 60.0))
        result = validate(step, spec_base, mat_pla)
        assert result.passed, result.reason

    def test_exceeds_x_fails(self, spec_base, mat_pla):
        from benchmark.geometry import validate

        step = _make_step_bytes(_box(110.0, 60.0, 60.0))  # 110 > 100 limit
        result = validate(step, spec_base, mat_pla)
        assert not result.passed
        assert "build volume" in result.reason.lower()

    def test_exceeds_y_fails(self, spec_base, mat_pla):
        from benchmark.geometry import validate

        step = _make_step_bytes(_box(80.0, 90.0, 60.0))  # 90 > 80 limit
        result = validate(step, spec_base, mat_pla)
        assert not result.passed
        assert "build volume" in result.reason.lower()

    def test_exactly_at_limit_passes(self, spec_base, mat_pla):
        from benchmark.geometry import validate

        bvol = spec_base["constraints"]["build_volume_mm"]
        step = _make_step_bytes(_box(bvol[0], bvol[1], bvol[2]))
        result = validate(step, spec_base, mat_pla)
        assert result.passed, result.reason

    def test_mass_populated_on_pass(self, spec_base, mat_pla):
        from benchmark.geometry import validate

        step = _make_step_bytes(_box(50.0, 50.0, 50.0))
        result = validate(step, spec_base, mat_pla)
        assert result.passed, result.reason
        assert result.mass_grams > 0
        # PLA at 1.24 g/cm³: 50³ mm³ = 125_000 mm³ = 125 cm³ → 155 g
        expected = 125_000 * 1240.0 * 1e-6
        assert abs(result.mass_grams - expected) < 1.0  # within 1 g


# ---------------------------------------------------------------------------
# Wall thickness checks
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not GEOMETRY_AVAILABLE, reason="OCP not installed")
class TestWallThickness:
    def test_thick_block_passes(self, spec_base, mat_pla):
        from benchmark.geometry import validate

        # 20mm in every direction — well above 1.2mm minimum
        step = _make_step_bytes(_box(50.0, 50.0, 20.0))
        result = validate(step, spec_base, mat_pla)
        assert result.passed, result.reason

    def test_thin_plate_fails(self, spec_base, mat_pla):
        from benchmark.geometry import validate

        # 0.5mm Z-thickness is below the 1.2mm minimum
        step = _make_step_bytes(_box(80.0, 60.0, 0.5))
        result = validate(step, spec_base, mat_pla)
        assert not result.passed
        assert "wall" in result.reason.lower() or "thin" in result.reason.lower()

    def test_exact_minimum_plus_tolerance_passes(self, spec_base, mat_pla):
        from benchmark.geometry import validate

        # 1.2mm + 0.1mm tolerance + 0.1mm margin = 1.4mm — should pass
        step = _make_step_bytes(_box(50.0, 50.0, 1.4))
        result = validate(step, spec_base, mat_pla)
        assert result.passed, result.reason

    def test_custom_min_wall_respected(self, spec_base, mat_pla):
        from benchmark.geometry import validate

        spec = dict(spec_base)
        spec["constraints"] = dict(spec_base["constraints"])
        spec["constraints"]["min_wall_thickness_mm"] = 5.0  # stricter

        # 4mm plate is below the new 5mm minimum
        step = _make_step_bytes(_box(80.0, 60.0, 4.0))
        result = validate(step, spec, mat_pla)
        assert not result.passed
        assert "wall" in result.reason.lower() or "thin" in result.reason.lower()


# ---------------------------------------------------------------------------
# GeometryResult fields
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not GEOMETRY_AVAILABLE, reason="OCP not installed")
class TestGeometryResult:
    def test_bounding_box_populated(self, spec_base, mat_pla):
        from benchmark.geometry import validate

        step = _make_step_bytes(_box(30.0, 40.0, 20.0))
        result = validate(step, spec_base, mat_pla)
        assert result.passed, result.reason
        assert result.bounding_box_mm is not None
        dx, dy, dz = result.bounding_box_mm
        assert abs(dx - 30.0) < 1.0
        assert abs(dy - 40.0) < 1.0
        assert abs(dz - 20.0) < 1.0

    def test_failed_result_has_empty_bbox(self, spec_base, mat_pla):
        from benchmark.geometry import validate

        # Box exceeds build volume — result should fail with no bbox
        step = _make_step_bytes(_box(200.0, 60.0, 60.0))
        result = validate(step, spec_base, mat_pla)
        assert not result.passed
        assert result.bounding_box_mm is None

    def test_invalid_step_bytes_fails_gracefully(self, spec_base, mat_pla):
        from benchmark.geometry import validate

        result = validate(b"this is not a STEP file", spec_base, mat_pla)
        assert not result.passed
        assert result.reason != ""

    def test_empty_bytes_fails_gracefully(self, spec_base, mat_pla):
        from benchmark.geometry import validate

        result = validate(b"", spec_base, mat_pla)
        assert not result.passed
