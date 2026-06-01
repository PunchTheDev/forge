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
