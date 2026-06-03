"""Catalog ingest pipeline: Thingiverse → Forge specs.

Fetches things from Thingiverse, derives a spec theme from each one,
and generates a deterministic Forge spec using specs/generator.py.

Designed to run periodically (e.g. before each competition round) to
produce a fresh, rotating problem set without manual curation.

Usage:
    python -m catalog.ingest --n 100 --out-dir specs/catalog/round_002/ --seed 99
    python -m catalog.ingest --dry-run --n 10
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from catalog.theme import theme_from_thing
from catalog.thingiverse import ThingiverseClient
from specs.generator import generate as generate_spec


def ingest(
    n: int,
    out_dir: Path,
    seed: int = 0,
    api_key: str | None = None,
    scoring_metric: str = "mass_grams",
    dry_run: bool = False,
) -> list[dict]:
    """Fetch n things from Thingiverse and write specs to out_dir.

    Returns list of generated spec dicts.
    """
    key = api_key or os.environ.get("THINGIVERSE_KEY")
    if not key:
        raise RuntimeError(
            "THINGIVERSE_KEY not set. "
            "Get a key at https://www.thingiverse.com/developers and set it."
        )

    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    specs: list[dict] = []
    seen_ids: set[int] = set()

    with ThingiverseClient(api_key=key) as client:
        for thing in client.bulk_fetch(per_query=max(50, n)):
            if len(specs) >= n:
                break
            if thing["id"] in seen_ids:
                continue
            seen_ids.add(thing["id"])

            theme = theme_from_thing(thing)

            # Derive a deterministic per-spec seed from master seed + thing ID
            spec_seed = _derive_seed(seed, thing["id"])
            spec_id = f"th_{thing['id']}"

            spec = generate_spec(
                spec_id=spec_id,
                tier=theme.tier,
                seed=spec_seed,
                scoring_metric=scoring_metric,
            )

            # Annotate with Thingiverse attribution
            spec["source"] = {
                "platform": "thingiverse",
                "thing_id": theme.thing_id,
                "url": theme.source_url,
                "thumbnail": theme.thumbnail,
                "original_name": thing["name"],
            }
            spec["name"] = f"{theme.name_prefix} [{theme.tier}]"

            specs.append(spec)

            if not dry_run:
                path = out_dir / f"{spec_id}.json"
                path.write_text(json.dumps(spec, indent=2))
                print(f"  wrote {path}  ({theme.tier}, {spec['material']})")
            else:
                print(f"  [dry-run] {spec_id}: {spec['name']} — {theme.tier} / {spec['material']}")

    print(f"\nIngested {len(specs)} specs from Thingiverse.")
    return specs


def _derive_seed(master_seed: int, thing_id: int) -> int:
    """Deterministically derive a per-spec seed from master + thing ID."""
    h = hashlib.sha256(f"{master_seed}:{thing_id}".encode()).digest()
    return int.from_bytes(h[:4], "big")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Thingiverse things as Forge specs."
    )
    parser.add_argument("--n", type=int, default=50, help="Number of specs to generate")
    parser.add_argument("--out-dir", type=Path, default=Path("specs/catalog/"), help="Output directory")
    parser.add_argument("--seed", type=int, default=0, help="Master random seed")
    parser.add_argument("--metric", choices=["mass_grams", "stiffness_to_weight", "deflection_mm"], default="mass_grams")
    parser.add_argument("--api-key", default=None, help="Thingiverse API key (or set THINGIVERSE_KEY)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    args = parser.parse_args()

    ingest(
        n=args.n,
        out_dir=args.out_dir,
        seed=args.seed,
        scoring_metric=args.metric,
        api_key=args.api_key,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
