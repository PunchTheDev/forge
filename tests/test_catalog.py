"""Tests for catalog/thingiverse and catalog/theme modules."""

import pytest

from catalog.theme import theme_from_thing, _infer_tier, _infer_material, _clean_name


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_thing(**kwargs):
    defaults = {
        "id": 12345,
        "name": "Wall Mount Bracket",
        "description": "A simple bracket for mounting to a wall.",
        "url": "https://www.thingiverse.com/thing:12345",
        "thumbnail": "",
        "tags": ["bracket", "mount", "wall"],
        "like_count": 10,
        "collect_count": 5,
        "category": "Tools",
    }
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# Tier inference
# ---------------------------------------------------------------------------

def test_tier_default_medium():
    thing = _make_thing(tags=["bracket"], description="a generic bracket")
    theme = theme_from_thing(thing)
    assert theme.tier == "medium"


def test_tier_hard_on_structural_keywords():
    thing = _make_thing(
        tags=["structural", "industrial", "load-bearing"],
        description="Heavy-duty aluminum cantilever bracket",
    )
    theme = theme_from_thing(thing)
    assert theme.tier == "hard"


def test_tier_easy_on_lightweight_keywords():
    thing = _make_thing(
        tags=["shelf", "lightweight", "simple", "desk"],
        description="Simple small cable holder",
    )
    theme = theme_from_thing(thing)
    assert theme.tier == "easy"


# ---------------------------------------------------------------------------
# Material inference
# ---------------------------------------------------------------------------

def test_material_defaults_to_pla():
    assert _infer_material("simple plastic bracket") == "pla"


def test_material_aluminum_from_tag():
    assert _infer_material("cnc aluminum bracket") == "aluminum_6061"


def test_material_petg_from_description():
    assert _infer_material("industrial nylon engineering bracket") == "petg"


# ---------------------------------------------------------------------------
# Name cleaning
# ---------------------------------------------------------------------------

def test_clean_name_strips_version():
    assert _clean_name("Bracket v2.1") == "Bracket"


def test_clean_name_strips_extension():
    assert _clean_name("bracket_mount.stl") == "bracket_mount"


def test_clean_name_trims_long_name():
    long = "A" * 100
    assert len(_clean_name(long)) <= 60


def test_clean_name_fallback():
    assert _clean_name("") == "Bracket"


# ---------------------------------------------------------------------------
# theme_from_thing integration
# ---------------------------------------------------------------------------

def test_theme_from_thing_attribution():
    thing = _make_thing(
        id=99999,
        url="https://www.thingiverse.com/thing:99999",
        thumbnail="http://example.com/thumb.jpg",
    )
    theme = theme_from_thing(thing)
    assert theme.thing_id == 99999
    assert theme.source_url == "https://www.thingiverse.com/thing:99999"
    assert theme.thumbnail == "http://example.com/thumb.jpg"


def test_theme_from_thing_name_prefix():
    thing = _make_thing(name="Heavy Duty Wall Bracket v3.0")
    theme = theme_from_thing(thing)
    assert "v3" not in theme.name_prefix
    assert "Heavy Duty Wall Bracket" in theme.name_prefix
