"""Map a Thingiverse thing to a Forge spec theme.

A "theme" captures what kind of structural problem the Thingiverse part
represents — its difficulty, material, load range, and display name.
The theme feeds into specs/generator.py to produce a valid spec.

No geometry parsing. We infer theme purely from tags and description
so the catalog ingest pipeline is fast and API-key-only (no file downloads).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class SpecTheme:
    tier: str                # "easy" | "medium" | "hard"
    material_hint: str       # preferred material for generator
    name_prefix: str         # human-readable prefix for spec name
    source_url: str          # link back to Thingiverse thing
    thumbnail: str           # image for dashboard display
    thing_id: int            # Thingiverse thing ID (for dedup + attribution)


# Keyword → material preference mapping
_MATERIAL_HINTS: list[tuple[list[str], str]] = [
    (["aluminum", "aluminium", "metal", "steel", "cnc", "machined"], "aluminum_6061"),
    (["petg", "abs", "nylon", "engineering", "industrial"], "petg"),
    # default falls through to pla
]

# Tag/keyword → difficulty tier
_HARD_SIGNALS = [
    "structural", "load-bearing", "industrial", "heavy", "high-stress",
    "engineering", "cnc", "aluminum", "steel", "cantilever", "bracket-heavy",
]
_EASY_SIGNALS = [
    "shelf", "small", "lightweight", "desk", "cable", "organizer", "holder",
    "simple", "quick", "mini",
]


def theme_from_thing(thing: dict) -> SpecTheme:
    """Derive a SpecTheme from a normalized Thingiverse thing dict."""
    tags = thing.get("tags", [])
    desc = (thing.get("description", "") + " " + thing.get("name", "")).lower()
    all_text = " ".join(tags) + " " + desc

    tier = _infer_tier(all_text)
    material_hint = _infer_material(all_text)
    name_prefix = _clean_name(thing.get("name", "Part"))

    return SpecTheme(
        tier=tier,
        material_hint=material_hint,
        name_prefix=name_prefix,
        source_url=thing.get("url", ""),
        thumbnail=thing.get("thumbnail", ""),
        thing_id=thing["id"],
    )


def _infer_tier(text: str) -> str:
    hard_score = sum(1 for kw in _HARD_SIGNALS if kw in text)
    easy_score = sum(1 for kw in _EASY_SIGNALS if kw in text)
    if hard_score >= 2:
        return "hard"
    if easy_score >= 2:
        return "easy"
    return "medium"


def _infer_material(text: str) -> str:
    for keywords, material in _MATERIAL_HINTS:
        if any(kw in text for kw in keywords):
            return material
    return "pla"


def _clean_name(name: str) -> str:
    """Strip noise from Thingiverse names for use as spec name prefix."""
    # Remove version numbers, file extensions, common noise
    cleaned = re.sub(r"v\d+(\.\d+)*", "", name, flags=re.IGNORECASE)
    cleaned = re.sub(r"\.(stl|step|obj|3mf)$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:60] or "Bracket"
