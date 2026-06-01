"""Procedural spec generator — anti-saturation engine for Forge.

Generates parameterised bracket/mount specs so the problem set never
saturates. Each call to `generate()` produces a valid spec dict that can be
written to JSON and evaluated with benchmark/evaluate.py.

Usage:
    python -m specs.generator --n 5 --tier medium --seed 42 --out-dir specs/generated/
    python -m specs.generator --preview --seed 0
"""

from __future__ import annotations

import argparse
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Difficulty tiers
# ---------------------------------------------------------------------------

@dataclass
class Tier:
    name: str
    load_kg_range: tuple[float, float]      # suspended mass range
    arm_mm_range: tuple[float, float]       # cantilever arm length
    build_volume_range: tuple[tuple[float, float], ...]  # (min, max) per axis
    safety_factor: float
    min_wall_mm: float
    max_overhang_deg: float
    materials: list[str]


TIERS: dict[str, Tier] = {
    "easy": Tier(
        name="easy",
        load_kg_range=(10.0, 25.0),
        arm_mm_range=(60.0, 100.0),
        build_volume_range=((140.0, 200.0), (80.0, 120.0), (80.0, 120.0)),
        safety_factor=1.5,
        min_wall_mm=1.0,
        max_overhang_deg=50.0,
        materials=["pla", "petg"],
    ),
    "medium": Tier(
        name="medium",
        load_kg_range=(30.0, 60.0),
        arm_mm_range=(80.0, 130.0),
        build_volume_range=((120.0, 160.0), (70.0, 110.0), (70.0, 110.0)),
        safety_factor=2.0,
        min_wall_mm=1.2,
        max_overhang_deg=45.0,
        materials=["pla", "petg", "aluminum_6061"],
    ),
    "hard": Tier(
        name="hard",
        load_kg_range=(60.0, 120.0),
        arm_mm_range=(120.0, 180.0),
        build_volume_range=((100.0, 140.0), (60.0, 100.0), (60.0, 100.0)),
        safety_factor=2.5,
        min_wall_mm=1.5,
        max_overhang_deg=40.0,
        materials=["petg", "aluminum_6061"],
    ),
}

# Approximate density table (kg/m³) for baseline mass estimation.
_DENSITY: dict[str, float] = {
    "pla": 1240.0,
    "petg": 1270.0,
    "aluminum_6061": 2700.0,
}

G = 9.81  # m/s²


def _bolt_pattern(rng: random.Random, rows: int, cols: int, pitch: float) -> list[list[float]]:
    """Return a rectangular bolt pattern centred at origin, in mm."""
    holes = []
    for r in range(rows):
        for c in range(cols):
            holes.append([round(c * pitch, 1), round(r * pitch, 1)])
    return holes


def _baseline_mass(
    arm_mm: float,
    build_volume: list[float],
    material: str,
    safety_factor: float,
) -> float:
    """Very rough baseline: solid block scaled by arm ratio."""
    vol_mm3 = build_volume[0] * build_volume[1] * build_volume[2]
    vol_m3 = vol_mm3 * 1e-9
    density = _DENSITY[material]
    solid_mass_g = vol_m3 * density * 1000.0  # grams
    # Real brackets are 15–30% of solid; scale loosely by arm length
    fill_fraction = 0.10 + 0.05 * (arm_mm / 100.0)
    return round(solid_mass_g * fill_fraction, 1)


def generate(
    spec_id: str,
    tier: str = "medium",
    seed: int | None = None,
    version: str = "1.0",
) -> dict:
    """Generate one spec dict for the given tier."""
    if tier not in TIERS:
        raise ValueError(f"Unknown tier '{tier}'. Valid: {list(TIERS)}")

    t = TIERS[tier]
    rng = random.Random(seed)

    material = rng.choice(t.materials)
    load_kg = rng.uniform(*t.load_kg_range)
    load_n = round(load_kg * G, 2)
    arm_mm = round(rng.uniform(*t.arm_mm_range), 1)

    # Build volume: sample each axis independently
    bv = [
        round(rng.uniform(lo, hi), 1)
        for (lo, hi) in t.build_volume_range
    ]

    # Load point: midway up and in on Y/Z, arm_mm out on X
    load_point = [arm_mm, round(bv[1] / 2, 1), round(bv[2] / 2, 1)]

    # Bolt pattern: 2×2 or 3×2 depending on build height
    rows, cols = (2, 2) if bv[1] < 90 else (2, 3)
    pitch = round(rng.uniform(40.0, 65.0), 1)
    # Clamp pitch so bolts fit in build volume with margin
    max_pitch_y = (bv[1] - 20.0) / max(rows - 1, 1)
    max_pitch_x = (bv[0] - 20.0) / max(cols - 1, 1)
    pitch = round(min(pitch, max_pitch_y, max_pitch_x), 1)
    bolt_pattern = _bolt_pattern(rng, rows, cols, pitch)
    clearance_mm = rng.choice([5.5, 6.5, 7.0])

    baseline = _baseline_mass(arm_mm, bv, material, t.safety_factor)

    spec = {
        "id": spec_id,
        "version": version,
        "name": _name(tier, material, load_kg, arm_mm),
        "description": _description(load_kg, arm_mm, material, tier),
        "material": material,
        "constraints": {
            "load_newtons": load_n,
            "load_point_mm": load_point,
            "safety_factor": t.safety_factor,
            "bolt_pattern_mm": bolt_pattern,
            "bolt_diameter_clearance_mm": clearance_mm,
            "mount_face_x_mm": 0.0,
            "build_volume_mm": bv,
            "max_overhang_deg": t.max_overhang_deg,
            "min_wall_thickness_mm": t.min_wall_mm,
        },
        "scoring": {
            "metric": "mass_grams",
            "direction": "minimize",
            "baseline_mass_grams": baseline,
        },
    }
    return spec


def _name(tier: str, material: str, load_kg: float, arm_mm: float) -> str:
    mat_label = {"pla": "PLA", "petg": "PETG", "aluminum_6061": "Al6061"}[material]
    return f"Cantilever Bracket — {mat_label} — {load_kg:.0f} kg @ {arm_mm:.0f} mm [{tier}]"


def _description(load_kg: float, arm_mm: float, material: str, tier: str) -> str:
    mat_label = {"pla": "PLA (FDM)", "petg": "PETG (FDM)", "aluminum_6061": "Aluminum 6061-T6"}[material]
    return (
        f"A {tier}-difficulty cantilever bracket in {mat_label}. "
        f"Mounts flush to a vertical wall and cantilevers a {load_kg:.1f} kg load "
        f"{arm_mm:.0f} mm from the wall face. Minimize mass while surviving the load."
    )


def batch_generate(
    n: int,
    tier: str = "medium",
    seed: int = 0,
    id_prefix: str = "gen",
    version: str = "1.0",
) -> list[dict]:
    """Generate n specs, each with a deterministic per-spec seed derived from the master seed."""
    rng = random.Random(seed)
    specs = []
    for i in range(n):
        spec_seed = rng.randint(0, 2**31)
        spec_id = f"{id_prefix}_{i + 1:03d}_{tier}"
        specs.append(generate(spec_id, tier=tier, seed=spec_seed, version=version))
    return specs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Forge problem specs.")
    parser.add_argument("--n", type=int, default=3, help="Number of specs to generate")
    parser.add_argument("--tier", choices=list(TIERS), default="medium")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--id-prefix", default="gen")
    parser.add_argument("--out-dir", type=Path, default=None, help="Write specs to this directory")
    parser.add_argument("--preview", action="store_true", help="Pretty-print one spec and exit")
    args = parser.parse_args()

    if args.preview:
        spec = generate(f"{args.id_prefix}_preview", tier=args.tier, seed=args.seed)
        print(json.dumps(spec, indent=2))
        return

    specs = batch_generate(args.n, tier=args.tier, seed=args.seed, id_prefix=args.id_prefix)

    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        for spec in specs:
            path = args.out_dir / f"{spec['id']}.json"
            path.write_text(json.dumps(spec, indent=2))
            print(f"Wrote {path}")
    else:
        print(json.dumps(specs, indent=2))


if __name__ == "__main__":
    main()
