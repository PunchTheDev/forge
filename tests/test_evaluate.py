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
GEOMETRY_AVAILABLE = False
try:
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    GEOMETRY_AVAILABLE = True
except ImportError:
    pass


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
            "def generate(spec):\n"
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
            "def generate(spec):\n"
            "    raise RuntimeError('intentional failure')\n"
        )
        from benchmark.sandbox import run_agent
        result = run_agent(str(agent), SPEC)
        assert not result.success
        assert "RuntimeError" in result.error or "intentional" in result.error

    def test_agent_wrong_return_type(self, tmp_path):
        agent = tmp_path / "wrong_type_agent.py"
        agent.write_text(
            "def generate(spec):\n"
            "    return 'not bytes'\n"
        )
        from benchmark.sandbox import run_agent
        result = run_agent(str(agent), SPEC)
        assert not result.success
        assert "bytes" in result.error.lower()

    def test_valid_agent_returns_bytes(self, tmp_path):
        agent = tmp_path / "ok_agent.py"
        agent.write_text(
            "def generate(spec):\n"
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
