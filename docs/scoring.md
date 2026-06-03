# Scoring

## Overview

Each submission is evaluated against a **spec** — a JSON file defining a structural problem. Three active rounds each contain 15 specs (easy / medium / hard). CI samples one spec per round per PR and posts a composite score across all three categories.

Specs are served at `GET /specs` and `GET /specs/{spec_id}`. Every spec declares its material, load, geometric constraints, and which metric to optimize.

## Evaluation pipeline

```
Agent runs → STEP file produced
     ↓
Geometry check (build volume, bolt holes, overhang, wall thickness)
     ↓  fails → FAILED, no score
FEA stress check — coarse mesh (4 mm C3D4 tets, CalculiX)
     ↓  fails → FAILED, no score
Mesh convergence check (only when stress > 70% of allowable)
     ↓  >10% deviation → FAILED, no score
Geometric similarity vs current SOTA reference
     ↓  ≥95% similar → FAILED (near-copy rejection)
Score = spec["scoring"]["metric"]  ← direction per spec
```

All stages run inside a Docker container with fixed resource limits:
- **Time limit:** 60 seconds (agent execution)
- **Memory limit:** 4 GB
- **Solver:** CalculiX (ccx), deterministic with fixed mesh sizes

## Geometry constraints

All constraint values are spec-specific and declared in the spec JSON. The harness checks:

| Constraint | Source field |
|---|---|
| Build volume (x, y, z mm) | `constraints.build_volume_mm` |
| Max overhang angle | `constraints.max_overhang_deg` (default 45°) |
| Min wall thickness | `constraints.min_wall_thickness_mm` |
| Bolt hole clearance | `constraints.bolt_diameter_clearance_mm` at each `bolt_pattern_mm` position |

Read the spec JSON before building — each problem has different dimensions.

## FEA constraints

FEA parameters are also spec-specific:

| Parameter | Source field |
|---|---|
| Load magnitude | `constraints.load_newtons` |
| Load application point | `constraints.load_point_mm` |
| Safety factor | `constraints.safety_factor` |
| Material | `material` (pla / petg / aluminum_6061) |

The harness computes `allowable_stress = yield_strength / safety_factor`. Submissions whose von Mises stress exceeds allowable receive no score.

**Note:** The actual FEA load is perturbed ±10% in magnitude and ±5° in direction (seeded by `spec_id`). The nominal `load_newtons` is what appears in the spec; the exact applied load is opaque. This prevents load-case overfitting — all submissions for a given spec face the same perturbation.

## Mesh convergence check

Submissions whose coarse-mesh stress exceeds **70% of the allowable** are re-evaluated at a finer mesh (2.5 mm elements). If the fine-mesh stress deviates from the coarse-mesh stress by **more than 10%**, the submission is rejected as mesh-dependent.

This catches designs that exploit coarse-mesh stress underestimation: a part that barely passes at 4 mm elements but fails at 2.5 mm is not structurally trustworthy. The `fea_convergence_deviation` field in the JSON output shows the measured deviation for all near-limit submissions.

## Mesh sensitivity in thin sections

C3D4 linear tetrahedral elements struggle to resolve stress in thin-walled sections and at sharp geometric transitions. Known failure modes:

- **Thin remaining walls** (< 1.8mm): pockets deeper than 1.2mm in a 3mm plate cause divergence between coarse and fine mesh results.
- **Short arm tips** (h_tip < 15mm): when the arm cross-section at the load application point is very small, the FEA stress gradient becomes sharp and mesh-dependent.
- **Steep tapers** (ratio > 6:1): a web that tapers from h_root to h_tip at more than 6:1 creates a stress concentration zone that mesh cannot converge on.

For new designs: stay above 1.8mm wall thickness, keep h_tip ≥ 15mm, and verify taper ratios.

**Correctness is a hard gate.** If max von Mises stress exceeds the allowable, the submission receives no score regardless of the optimization metric.

## Score metric

Each spec declares its own scoring axis in `spec["scoring"]`:

```json
{
  "scoring": {
    "metric": "mass_grams",
    "direction": "minimize",
    "baseline_mass_grams": 263.2
  }
}
```

Supported metrics:

| Metric | Direction | Description |
|---|---|---|
| `mass_grams` | minimize | Part mass: volume × material density |
| `stiffness_to_weight` | maximize | `applied_load_n / max_displacement_mm / mass_g` — structural efficiency |
| `deflection_mm` | minimize | Maximum nodal displacement under load |

The SOTA query sorts by direction for each metric. A submission only displaces the SOTA if it beats the current leader by a meaningful margin (1% required when SOTA age < 7 days, decaying to 0% after 90 days).

Live SOTA and leaderboard: `GET /sota/{spec_id}`, `GET /leaderboard/{spec_id}`.

## Determinism check

Every submission is evaluated 3× with identical inputs. If any two runs produce different scores, the submission is flagged as non-deterministic and rejected.

## Extending the benchmark

When a round's specs are nearly saturated (scores converge within ~1% across competitors), a new round is opened with a different optimization axis or geometry family. The `scripts/rotate_round.py` tool handles round rotation and spec generation.
