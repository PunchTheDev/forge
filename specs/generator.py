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
        materials=["petg", "aluminum_6061", "stainless_316"],
    ),
}

# Approximate density table (kg/m³) for baseline mass estimation.
_DENSITY: dict[str, float] = {
    "pla": 1240.0,
    "petg": 1270.0,
    "aluminum_6061": 2700.0,
    "stainless_316": 7990.0,
}

# Approximate Young's modulus (MPa) for baseline stiffness estimation.
_YOUNGS_MPa: dict[str, float] = {
    "pla": 3500.0,
    "petg": 2100.0,
    "aluminum_6061": 68900.0,
    "stainless_316": 193000.0,
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


def _baseline_stiffness_to_weight(
    load_n: float,
    arm_mm: float,
    build_volume: list[float],
    material: str,
) -> float:
    """Very rough stiffness-to-weight baseline for a cantilevered beam.

    Uses Euler-Bernoulli tip deflection: δ = FL³/(3EI) for a rectangular
    cross-section of the build-volume face. This is a conservative solid-beam
    upper bound; real topology-optimised brackets do better.
    Returns N/(mm·g).
    """
    E = _YOUNGS_MPa[material]  # MPa = N/mm²
    L = arm_mm
    # Cross-section: use Y×Z face of build volume
    b = build_volume[1]  # width (mm)
    h = build_volume[2]  # height (mm)
    I = (b * h**3) / 12.0  # mm⁴
    # Tip deflection of solid-beam upper bound
    delta_mm = (load_n * L**3) / (3.0 * E * I)
    if delta_mm <= 0:
        return 0.0
    stiffness = load_n / delta_mm  # N/mm
    mass_g = _baseline_mass(arm_mm, build_volume, material, safety_factor=1.0)
    if mass_g <= 0:
        return 0.0
    return round(stiffness / mass_g, 6)  # N/(mm·g)


def _baseline_deflection_mm(
    load_n: float,
    arm_mm: float,
    build_volume: list[float],
    material: str,
) -> float:
    """Euler-Bernoulli tip deflection of a solid rectangular cantilever beam.

    Serves as the baseline upper bound for deflection_mm: a naive solid-block
    design with the full build-volume cross-section. Real optimised designs
    should achieve lower deflection by stacking material efficiently.
    Returns mm.
    """
    E = _YOUNGS_MPa[material]
    L = arm_mm
    b = build_volume[1]
    h = build_volume[2]
    I = (b * h**3) / 12.0
    delta_mm = (load_n * L**3) / (3.0 * E * I)
    return round(max(delta_mm, 1e-6), 6)


def generate(
    spec_id: str,
    tier: str = "medium",
    seed: int | None = None,
    version: str = "1.0",
    scoring_metric: str = "mass_grams",
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

    if scoring_metric == "stiffness_to_weight":
        baseline_stw = _baseline_stiffness_to_weight(load_n, arm_mm, bv, material)
        scoring_block = {
            "metric": "stiffness_to_weight",
            "direction": "maximize",
            "baseline_stiffness_to_weight": baseline_stw,
        }
        obj_phrase = "Maximize stiffness-to-weight ratio while surviving the load."
    elif scoring_metric == "deflection_mm":
        baseline_defl = _baseline_deflection_mm(load_n, arm_mm, bv, material)
        scoring_block = {
            "metric": "deflection_mm",
            "direction": "minimize",
            "baseline_deflection_mm": baseline_defl,
        }
        obj_phrase = "Minimize tip deflection under load — maximize absolute stiffness regardless of mass."
    else:
        baseline_mass = _baseline_mass(arm_mm, bv, material, t.safety_factor)
        scoring_block = {
            "metric": "mass_grams",
            "direction": "minimize",
            "baseline_mass_grams": baseline_mass,
        }
        obj_phrase = "Minimize mass while surviving the load."

    spec = {
        "id": spec_id,
        "version": version,
        "name": _name(tier, material, load_kg, arm_mm, scoring_metric),
        "description": _description(load_kg, arm_mm, material, tier, obj_phrase),
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
        "scoring": scoring_block,
    }
    return spec


_MAT_LABEL: dict[str, str] = {
    "pla": "PLA",
    "petg": "PETG",
    "aluminum_6061": "Al6061",
    "stainless_316": "SS316",
}

_MAT_LABEL_LONG: dict[str, str] = {
    "pla": "PLA (FDM)",
    "petg": "PETG (FDM)",
    "aluminum_6061": "Aluminum 6061-T6",
    "stainless_316": "Stainless Steel 316",
}


def _name(tier: str, material: str, load_kg: float, arm_mm: float, metric: str = "mass_grams") -> str:
    mat_label = _MAT_LABEL.get(material, material)
    metric_tag = (
        "stiffness" if metric == "stiffness_to_weight"
        else "deflection" if metric == "deflection_mm"
        else "mass"
    )
    return f"Cantilever Bracket — {mat_label} — {load_kg:.0f} kg @ {arm_mm:.0f} mm [{tier}, {metric_tag}]"


def _description(load_kg: float, arm_mm: float, material: str, tier: str, obj_phrase: str) -> str:
    mat_label = _MAT_LABEL_LONG.get(material, material)
    return (
        f"A {tier}-difficulty cantilever bracket in {mat_label}. "
        f"Mounts flush to a vertical wall and cantilevers a {load_kg:.1f} kg load "
        f"{arm_mm:.0f} mm from the wall face. {obj_phrase}"
    )


def batch_generate(
    n: int,
    tier: str = "medium",
    seed: int = 0,
    id_prefix: str = "gen",
    version: str = "1.0",
    scoring_metric: str = "mass_grams",
) -> list[dict]:
    """Generate n specs, each with a deterministic per-spec seed derived from the master seed."""
    rng = random.Random(seed)
    specs = []
    for i in range(n):
        spec_seed = rng.randint(0, 2**31)
        spec_id = f"{id_prefix}_{i + 1:03d}_{tier}"
        specs.append(generate(spec_id, tier=tier, seed=spec_seed, version=version, scoring_metric=scoring_metric))
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
    parser.add_argument("--metric", choices=["mass_grams", "stiffness_to_weight", "deflection_mm"], default="mass_grams")
    parser.add_argument("--out-dir", type=Path, default=None, help="Write specs to this directory")
    parser.add_argument("--preview", action="store_true", help="Pretty-print one spec and exit")
    args = parser.parse_args()

    if args.preview:
        spec = generate(f"{args.id_prefix}_preview", tier=args.tier, seed=args.seed, scoring_metric=args.metric)
        print(json.dumps(spec, indent=2))
        return

    specs = batch_generate(args.n, tier=args.tier, seed=args.seed, id_prefix=args.id_prefix, scoring_metric=args.metric)

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
