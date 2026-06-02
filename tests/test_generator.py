"""Tests for specs/generator.py — determinism, metric variants, and material coverage."""
import pytest
from specs.generator import generate, batch_generate, TIERS


def test_generate_mass_deterministic():
    a = generate("test_mass", tier="medium", seed=42)
    b = generate("test_mass", tier="medium", seed=42)
    assert a == b


def test_generate_stiffness_deterministic():
    a = generate("test_stw", tier="hard", seed=99, scoring_metric="stiffness_to_weight")
    b = generate("test_stw", tier="hard", seed=99, scoring_metric="stiffness_to_weight")
    assert a == b


def test_generate_mass_fields():
    spec = generate("x", tier="easy", seed=1)
    assert spec["scoring"]["metric"] == "mass_grams"
    assert spec["scoring"]["direction"] == "minimize"
    assert "baseline_mass_grams" in spec["scoring"]
    assert spec["scoring"]["baseline_mass_grams"] > 0


def test_generate_stiffness_fields():
    spec = generate("x", tier="medium", seed=1, scoring_metric="stiffness_to_weight")
    assert spec["scoring"]["metric"] == "stiffness_to_weight"
    assert spec["scoring"]["direction"] == "maximize"
    assert "baseline_stiffness_to_weight" in spec["scoring"]
    assert spec["scoring"]["baseline_stiffness_to_weight"] > 0


def test_generate_invalid_tier():
    with pytest.raises(ValueError, match="Unknown tier"):
        generate("x", tier="extreme")


def test_hard_tier_includes_stainless():
    """stainless_316 must be reachable in the hard tier."""
    materials_seen = set()
    for seed in range(50):
        spec = generate("x", tier="hard", seed=seed)
        materials_seen.add(spec["material"])
    assert "stainless_316" in materials_seen, "stainless_316 never sampled in hard tier"


def test_batch_generate_ids_unique():
    specs = batch_generate(5, tier="medium", seed=0, id_prefix="r02")
    ids = [s["id"] for s in specs]
    assert len(ids) == len(set(ids))


def test_batch_generate_stiffness():
    specs = batch_generate(3, tier="easy", seed=400, id_prefix="r02", scoring_metric="stiffness_to_weight")
    for spec in specs:
        assert spec["scoring"]["metric"] == "stiffness_to_weight"


def test_all_tiers_generate():
    for tier in TIERS:
        spec = generate(f"test_{tier}", tier=tier, seed=7)
        assert spec["material"] in TIERS[tier].materials
        assert "constraints" in spec
        assert spec["constraints"]["load_newtons"] > 0
