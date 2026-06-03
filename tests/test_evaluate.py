"""
Forge benchmark test suite.

Tests that don't require CalculiX or gmsh run in any environment.
FEA tests are skipped if `ccx` is not on PATH.
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

SPEC_PATH = Path(__file__).parent.parent / "specs" / "001_bracket.json"
SPEC = json.loads(SPEC_PATH.read_text())

CCX_AVAILABLE = shutil.which("ccx") is not None


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------

class TestMaterials:
    def test_pla_properties(self):
        from benchmark.materials import get
        mat = get("pla")
        assert mat["youngs_modulus_mpa"] == 3500.0
        assert mat["yield_stress_mpa"] == 50.0
        assert mat["density_kg_m3"] == 1240.0

    def test_unknown_material_raises(self):
        from benchmark.materials import get
        with pytest.raises(ValueError, match="Unknown material"):
            get("unobtainium")

    def test_all_materials_have_required_keys(self):
        from benchmark.materials import MATERIALS
        required = {"youngs_modulus_mpa", "poisson_ratio", "yield_stress_mpa", "density_kg_m3"}
        for name, props in MATERIALS.items():
            missing = required - props.keys()
            assert not missing, f"Material '{name}' missing keys: {missing}"


# ---------------------------------------------------------------------------
# Spec schema
# ---------------------------------------------------------------------------

class TestSpec:
    def test_spec_loads(self):
        assert SPEC["id"] == "001_bracket"
        assert SPEC["material"] == "pla"

    def test_spec_has_required_constraint_keys(self):
        c = SPEC["constraints"]
        assert "load_newtons" in c
        assert "safety_factor" in c
        assert "bolt_pattern_mm" in c
        assert "build_volume_mm" in c
        assert "max_overhang_deg" in c
        assert "min_wall_thickness_mm" in c

    def test_spec_safety_factor_reasonable(self):
        assert 1.0 < SPEC["constraints"]["safety_factor"] <= 5.0

    def test_bolt_pattern_has_four_holes(self):
        assert len(SPEC["constraints"]["bolt_pattern_mm"]) == 4


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------

class TestSandbox:
    def test_agent_timeout(self, tmp_path):
        agent = tmp_path / "slow_agent.py"
        agent.write_text(
            "import time\n"
            "def generate(spec, llm):\n"
            "    time.sleep(120)\n"
            "    return b''\n"
        )
        from benchmark.sandbox import run_agent, TIMEOUT_SECONDS
        # Patch timeout to 2s for speed
        with patch("benchmark.sandbox.TIMEOUT_SECONDS", 2):
            result = run_agent(str(agent), SPEC)
        assert not result.success
        assert "timed out" in result.error.lower()

    def test_agent_exception_propagates(self, tmp_path):
        agent = tmp_path / "bad_agent.py"
        agent.write_text(
            "def generate(spec, llm):\n"
            "    raise RuntimeError('intentional failure')\n"
        )
        from benchmark.sandbox import run_agent
        result = run_agent(str(agent), SPEC)
        assert not result.success
        assert "RuntimeError" in result.error or "intentional" in result.error

    def test_agent_wrong_return_type(self, tmp_path):
        agent = tmp_path / "wrong_type_agent.py"
        agent.write_text(
            "def generate(spec, llm):\n"
            "    return 'not bytes'\n"
        )
        from benchmark.sandbox import run_agent
        result = run_agent(str(agent), SPEC)
        assert not result.success
        assert "bytes" in result.error.lower()

    def test_valid_agent_returns_bytes(self, tmp_path):
        agent = tmp_path / "ok_agent.py"
        agent.write_text(
            "def generate(spec, llm):\n"
            "    return b'fake step content'\n"
        )
        from benchmark.sandbox import run_agent
        result = run_agent(str(agent), SPEC)
        assert result.success
        assert result.step_bytes == b"fake step content"


# ---------------------------------------------------------------------------
# SOTA integrity
# ---------------------------------------------------------------------------

class TestSOTA:
    def test_sota_json_valid(self):
        sota_path = Path(__file__).parent.parent / "sota" / "score.json"
        data = json.loads(sota_path.read_text())
        assert "score_grams" in data
        assert "spec_id" in data
        assert data["score_grams"] > 0

    def test_sota_spec_id_matches(self):
        sota_path = Path(__file__).parent.parent / "sota" / "score.json"
        data = json.loads(sota_path.read_text())
        assert data["spec_id"] == SPEC["id"]


# ---------------------------------------------------------------------------
# FEA oracle hardening
# ---------------------------------------------------------------------------

class TestFEAHardening:
    """Verify anti-gaming rejection paths in fea.py without running CalculiX."""

    def _fake_step(self) -> bytes:
        return b"fake step bytes"

    def _mat(self):
        from benchmark.materials import get
        return get("pla")

    def test_degenerate_mesh_rejected(self):
        """Fewer than MIN_ELEMENTS tetrahedra → FEAResult.passed=False."""
        from benchmark import fea

        # Build a tiny mesh: 2 nodes, 2 elements (well below MIN_ELEMENTS=100)
        tiny_nodes = {1: (0.0, 0.0, 0.0), 2: (10.0, 0.0, 0.0)}
        tiny_elements = [(1, 2, 1, 2)] * 2  # only 2 elements

        with patch("benchmark.fea._mesh", return_value=(tiny_nodes, tiny_elements)):
            result = fea.run(self._fake_step(), SPEC, self._mat())

        assert not result.passed
        assert "degenerate" in result.reason.lower() or "elements" in result.reason.lower()

    def test_load_node_minimum_enforced(self):
        """Fewer than MIN_LOAD_NODES near load point → rejection."""
        from benchmark import fea

        # Generate enough elements to pass the element count gate.
        # Place nodes far from the load point so load_nodes comes back < MIN_LOAD_NODES.
        load_pt = SPEC["constraints"]["load_point_mm"]  # [100, 25, 25]
        # All nodes at bolt face (x=0) — far from load_point — so no load nodes found.
        nodes = {i: (0.0, float(i % 10), float(i // 10)) for i in range(1, 201)}
        elements = [(i, i+1, i+2, i+3) for i in range(1, 150)]

        with patch("benchmark.fea._mesh", return_value=(nodes, elements)):
            result = fea.run(self._fake_step(), SPEC, self._mat())

        assert not result.passed
        assert "load" in result.reason.lower()

    def test_fea_result_carries_element_count(self):
        """element_count and load_node_count are populated on success path up to FEA stage."""
        from benchmark import fea

        # Patch mesh to return a plausible minimal set; it will fail at the
        # load-node stage, but element_count must be populated.
        nodes = {i: (0.0, float(i % 10), float(i // 10)) for i in range(1, 201)}
        elements = [(i, i+1, i+2, i+3) for i in range(1, 150)]

        with patch("benchmark.fea._mesh", return_value=(nodes, elements)):
            result = fea.run(self._fake_step(), SPEC, self._mat())

        assert result.element_count >= 100 or result.element_count > 0


# ---------------------------------------------------------------------------
# Mesh convergence check
# ---------------------------------------------------------------------------

class TestMeshConvergence:
    """Verify the two-pass convergence check in fea.run() without running CalculiX."""

    def _mat(self):
        from benchmark.materials import get
        return get("pla")

    def _passing_result(self, stress_mpa: float, elem_count: int = 500) -> "FEAResult":
        from benchmark.fea import FEAResult
        allowable = self._mat()["yield_stress_mpa"] / SPEC["constraints"]["safety_factor"]
        return FEAResult(
            passed=True,
            max_stress_mpa=stress_mpa,
            allowable_mpa=allowable,
            element_count=elem_count,
            load_node_count=20,
        )

    def test_convergence_not_triggered_when_stress_low(self):
        """Stress well below 40% of allowable: fine-mesh pass not run."""
        from benchmark import fea

        mat = self._mat()
        allowable = mat["yield_stress_mpa"] / SPEC["constraints"]["safety_factor"]
        # 30% of allowable — below CONVERGENCE_TRIGGER_FRACTION (0.40)
        low_stress = allowable * 0.30
        coarse_result = self._passing_result(low_stress)

        with patch("benchmark.fea._run_at_mesh_size", return_value=coarse_result) as mock_run:
            result = fea.run(b"fake", SPEC, mat)

        # Only one call: the coarse pass
        assert mock_run.call_count == 1
        assert result.passed
        assert result.convergence_deviation is None

    def test_convergence_triggered_when_stress_near_limit(self):
        """Stress above 40% of allowable: fine-mesh pass runs."""
        from benchmark import fea

        mat = self._mat()
        allowable = mat["yield_stress_mpa"] / SPEC["constraints"]["safety_factor"]
        high_stress = allowable * 0.85  # above CONVERGENCE_TRIGGER_FRACTION

        # Both passes return similar stress (< 10% deviation) → should pass
        coarse = self._passing_result(high_stress)
        fine = self._passing_result(high_stress * 1.05)  # 5% deviation — under threshold

        with patch("benchmark.fea._run_at_mesh_size", side_effect=[coarse, fine]) as mock_run:
            result = fea.run(b"fake", SPEC, mat)

        assert mock_run.call_count == 2
        assert result.passed
        assert result.convergence_deviation is not None
        assert result.convergence_deviation < 0.10

    def test_convergence_failure_rejects_submission(self):
        """Fine-mesh stress deviates >10% from coarse → rejection."""
        from benchmark import fea

        mat = self._mat()
        allowable = mat["yield_stress_mpa"] / SPEC["constraints"]["safety_factor"]
        high_stress = allowable * 0.85

        coarse = self._passing_result(high_stress)
        # Fine mesh returns 20% higher stress — should trigger rejection
        fine = self._passing_result(high_stress * 1.20)

        with patch("benchmark.fea._run_at_mesh_size", side_effect=[coarse, fine]):
            result = fea.run(b"fake", SPEC, mat)

        assert not result.passed
        assert "mesh-dependent" in result.reason.lower()
        assert result.convergence_deviation is not None
        assert result.convergence_deviation > 0.10

    def test_convergence_deviation_in_result_on_pass(self):
        """Passing submission with high stress reports convergence_deviation."""
        from benchmark import fea

        mat = self._mat()
        allowable = mat["yield_stress_mpa"] / SPEC["constraints"]["safety_factor"]
        high_stress = allowable * 0.80

        coarse = self._passing_result(high_stress)
        fine = self._passing_result(high_stress * 1.03)  # 3% — passes

        with patch("benchmark.fea._run_at_mesh_size", side_effect=[coarse, fine]):
            result = fea.run(b"fake", SPEC, mat)

        assert result.passed
        assert result.convergence_deviation is not None
        assert abs(result.convergence_deviation - 0.03) < 0.005


# ---------------------------------------------------------------------------
# Geometric similarity
# ---------------------------------------------------------------------------

class TestSimilarity:
    """Unit tests for benchmark.similarity. No OCP required — patches _sample_surface."""

    def _pts(self, seed: int, n: int = 200, scale: float = 1.0) -> "np.ndarray":
        import numpy as np
        rng = np.random.default_rng(seed)
        return rng.random((n, 3)) * scale * 100.0

    def test_identical_inputs_score_one(self):
        import numpy as np
        from benchmark.similarity import compute

        pts = self._pts(42)
        with patch("benchmark.similarity._sample_surface", return_value=pts):
            score = compute(b"a", b"b")
        assert score >= 0.99, f"Identical point clouds should score ~1.0, got {score}"

    def test_different_inputs_score_low(self):
        import numpy as np
        from benchmark.similarity import compute

        pts_a = self._pts(1, scale=1.0)         # cluster near origin
        pts_b = self._pts(2, scale=1.0) + 500   # cluster 500 mm away

        call_count = [0]

        def mock_sample(step_bytes, n, seed):
            call_count[0] += 1
            return pts_a if call_count[0] == 1 else pts_b

        with patch("benchmark.similarity._sample_surface", side_effect=mock_sample):
            score = compute(b"a", b"b")
        assert score < 0.5, f"Well-separated point clouds should score < 0.5, got {score}"

    def test_degenerate_returns_zero(self):
        import numpy as np
        from benchmark.similarity import compute

        with patch("benchmark.similarity._sample_surface", return_value=np.zeros((0, 3))):
            score = compute(b"a", b"b")
        assert score == 0.0

    def test_compute_returns_float_in_range(self):
        import numpy as np
        from benchmark.similarity import compute

        pts_a = self._pts(10)
        pts_b = self._pts(11)  # slightly different

        call_count = [0]

        def mock_sample(step_bytes, n, seed):
            call_count[0] += 1
            return pts_a if call_count[0] == 1 else pts_b

        with patch("benchmark.similarity._sample_surface", side_effect=mock_sample):
            score = compute(b"a", b"b")
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# FRD displacement parsing
# ---------------------------------------------------------------------------

class TestFRDDisplacementParsing:
    """Unit tests for _parse_frd_displacement without running CalculiX."""

    def _write_frd(self, tmp_path, node_disps: list[tuple[int, float, float, float]]) -> str:
        """Write a minimal ASCII .frd file with a DISP block."""
        lines = [" 9999 FORGE TEST\n"]
        lines.append("  -4  DISP        4    4\n")
        lines.append(" -5  D1          4    0    0    1\n")
        lines.append(" -5  D2          4    0    0    2\n")
        lines.append(" -5  D3          4    0    0    3\n")
        lines.append(" -5  ALL         4    0    0    0    1ALL\n")
        for nid, u1, u2, u3 in node_disps:
            lines.append(f" -1{nid:10d}{u1:12.5E}{u2:12.5E}{u3:12.5E}\n")
        lines.append(" -3\n")
        frd_path = str(tmp_path / "job.frd")
        Path(frd_path).write_text("".join(lines))
        return frd_path

    def test_max_u3_extracted(self, tmp_path):
        from benchmark.fea import _parse_frd_displacement
        frd = self._write_frd(tmp_path, [
            (1, 0.001, 0.002, -0.010),
            (2, 0.000, 0.001, -0.025),  # largest |U3|
            (3, 0.002, 0.000, -0.005),
        ])
        result = _parse_frd_displacement(frd)
        assert result is not None
        assert abs(result - 0.025) < 1e-6

    def test_no_displacement_block_returns_none(self, tmp_path):
        from benchmark.fea import _parse_frd_displacement
        frd_path = str(tmp_path / "empty.frd")
        Path(frd_path).write_text(" 9999 FORGE TEST\n -3\n")
        result = _parse_frd_displacement(frd_path)
        assert result is None

    def test_abs_value_used(self, tmp_path):
        """Positive and negative U3 — max absolute value should win."""
        from benchmark.fea import _parse_frd_displacement
        frd = self._write_frd(tmp_path, [
            (1, 0.0, 0.0, 0.030),   # positive U3
            (2, 0.0, 0.0, -0.050),  # larger abs
        ])
        result = _parse_frd_displacement(frd)
        assert result is not None
        assert abs(result - 0.050) < 1e-6


# ---------------------------------------------------------------------------
# Multi-objective scoring
# ---------------------------------------------------------------------------

class TestMultiObjectiveScoring:
    """Tests for direction-aware scoring in evaluate.py."""

    def _mock_geo(self, mass=25.0, volume=10000.0):
        geo = MagicMock()
        geo.passed = True
        geo.mass_grams = mass
        geo.volume_mm3 = volume
        geo.reason = ""
        return geo

    def _mock_fea(self, disp_mm=0.1):
        from benchmark.fea import FEAResult
        allowable = 25.0
        return FEAResult(
            passed=True,
            max_stress_mpa=10.0,
            allowable_mpa=allowable,
            element_count=500,
            load_node_count=20,
            max_displacement_mm=disp_mm,
        )

    def test_mass_grams_score(self):
        from benchmark.evaluate import _compute_score
        geo = self._mock_geo(mass=25.0)
        fea_result = self._mock_fea()
        score = _compute_score(geo, fea_result, SPEC, "mass_grams")
        assert score == 25.0

    def test_volume_mm3_score(self):
        from benchmark.evaluate import _compute_score
        geo = self._mock_geo(volume=12345.0)
        fea_result = self._mock_fea()
        score = _compute_score(geo, fea_result, SPEC, "volume_mm3")
        assert score == 12345.0

    def test_stiffness_to_weight_score(self):
        from benchmark.evaluate import _compute_score
        geo = self._mock_geo(mass=25.0)
        # load = 464.48 N, disp = 0.1 mm → stiffness = 4644.8 N/mm
        # stiffness_to_weight = 4644.8 / 25.0 = 185.792
        fea_result = self._mock_fea(disp_mm=0.1)
        score = _compute_score(geo, fea_result, SPEC, "stiffness_to_weight")
        load_n = SPEC["constraints"]["load_newtons"]
        expected = (load_n / 0.1) / 25.0
        assert abs(score - expected) < 1e-4

    def test_stiffness_to_weight_zero_disp_raises(self):
        from benchmark.evaluate import _compute_score
        geo = self._mock_geo(mass=25.0)
        fea_result = self._mock_fea(disp_mm=0.0)
        with pytest.raises(ValueError, match="displacement"):
            _compute_score(geo, fea_result, SPEC, "stiffness_to_weight")

    def test_metrics_dict_has_expected_entries(self):
        from benchmark.evaluate import METRICS
        assert "mass_grams" in METRICS
        assert "volume_mm3" in METRICS
        assert "stiffness_to_weight" in METRICS
        assert METRICS["mass_grams"] == "minimize"
        assert METRICS["stiffness_to_weight"] == "maximize"


# ---------------------------------------------------------------------------
# geometry_only mode
# ---------------------------------------------------------------------------

class TestGeometryOnly:
    """Verify that geometry_only=True skips FEA and returns a mass score."""

    def _agent(self, tmp_path: Path, step_bytes: bytes = b"fakestep") -> Path:
        agent = tmp_path / "agent.py"
        content = repr(step_bytes)
        agent.write_text(f"def generate(spec, llm):\n    return {content}\n")
        return agent

    def _passing_geo(self, mass: float = 18.5):
        geo = MagicMock()
        geo.passed = True
        geo.mass_grams = mass
        geo.volume_mm3 = 7500.0
        geo.reason = ""
        return geo

    def _failing_geo(self, reason: str = "exceeds build volume"):
        geo = MagicMock()
        geo.passed = False
        geo.mass_grams = None
        geo.volume_mm3 = None
        geo.reason = reason
        return geo

    def test_geometry_only_skips_fea(self, tmp_path):
        """When geometry_only=True, fea.run must never be called."""
        from benchmark.evaluate import evaluate
        agent = self._agent(tmp_path)

        with patch("benchmark.evaluate.geometry.validate", return_value=self._passing_geo()), \
             patch("benchmark.evaluate.fea.run") as mock_fea:
            result = evaluate(str(agent), str(SPEC_PATH), geometry_only=True)

        mock_fea.assert_not_called()
        assert result.passed

    def test_geometry_only_returns_mass_score(self, tmp_path):
        """Score should equal the geometry mass estimate."""
        from benchmark.evaluate import evaluate
        agent = self._agent(tmp_path)

        with patch("benchmark.evaluate.geometry.validate", return_value=self._passing_geo(mass=22.3)):
            result = evaluate(str(agent), str(SPEC_PATH), geometry_only=True)

        assert result.passed
        assert result.score == pytest.approx(22.3)
        assert result.score_metric == "mass_grams"
        assert result.score_direction == "minimize"
        assert result.stage == "ok"

    def test_geometry_only_propagates_geometry_failure(self, tmp_path):
        """Geometry failure still surfaces correctly in geometry_only mode."""
        from benchmark.evaluate import evaluate
        agent = self._agent(tmp_path)

        with patch("benchmark.evaluate.geometry.validate",
                   return_value=self._failing_geo("exceeds build volume")):
            result = evaluate(str(agent), str(SPEC_PATH), geometry_only=True)

        assert not result.passed
        assert result.stage == "geometry"
        assert "build volume" in result.reason

    def test_geometry_only_agent_failure_still_reported(self, tmp_path):
        """Agent errors are reported even in geometry_only mode."""
        agent = tmp_path / "bad.py"
        agent.write_text("def generate(spec, llm):\n    raise RuntimeError('boom')\n")

        from benchmark.evaluate import evaluate
        result = evaluate(str(agent), str(SPEC_PATH), geometry_only=True)

        assert not result.passed
        assert result.stage == "agent"
