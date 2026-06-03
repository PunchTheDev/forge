"""Generate private held-out eval specs and print them as base64-encoded JSON.

These specs are NOT committed to the forge repo. The operator runs this script
once, then sets HIDDEN_SPECS_JSON=<output> as an environment variable on the
forge-api server. forge-api seeds them into the hidden_specs table on first
startup if that table is empty.

Usage:
    python scripts/generate_hidden_specs.py
    # Copy the printed value into HIDDEN_SPECS_JSON on the server.

Seeds 9000–9004: round_001 (mass_grams)
Seeds 9100–9104: round_002 (stiffness_to_weight)
Seeds 9200–9204: round_003 (deflection_mm)
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from specs.generator import batch_generate  # noqa: E402

ROUND_CONFIG = [
    ("round_001", "mass_grams",          "minimize", 9000),
    ("round_002", "stiffness_to_weight", "maximize", 9100),
    ("round_003", "deflection_mm",       "minimize", 9200),
]
TIERS = ["easy", "easy", "medium", "medium", "hard"]
SPECS_PER_ROUND = 5


def generate() -> list[dict]:
    hidden: list[dict] = []
    for round_id, metric, direction, seeds_base in ROUND_CONFIG:
        for i in range(SPECS_PER_ROUND):
            seed = seeds_base + i
            tier = TIERS[i]
            spec = batch_generate(n=1, tier=tier, seed=seed)[0]
            spec["id"] = f"hidden_{round_id}_{i + 1:03d}_{tier}"
            spec["round_id"] = round_id
            spec["scoring"] = {"metric": metric, "direction": direction}
            hidden.append(spec)
    return hidden


if __name__ == "__main__":
    specs = generate()
    payload = base64.b64encode(json.dumps(specs).encode()).decode()
    print(payload)
    print(f"\n# {len(specs)} specs generated. Set HIDDEN_SPECS_JSON=<above> on the server.", file=sys.stderr)
