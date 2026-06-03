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

## Cross-spec leaderboard (overall_score)

The per-spec leaderboard ranks contributors on a single spec. The **overall leaderboard** (`GET /leaderboard/overall`) ranks contributors across *all* 45 active-round specs.

### Philosophy

The goal is to reward the best **well-rounded CAD agent**, not a narrow specialist. An agent that achieves a 1% improvement on one mass spec while ignoring all stiffness and deflection specs should rank far below a generalist that competes meaningfully across every category.

This is enforced by **breadth normalization**: unentered specs count against you at the worst possible rank (1.0), so you cannot improve your overall score by cherry-picking only easy specs.

### Calculation

```
overall_score = mean(normalized_rank[i]) across ALL 45 active specs

where:
  normalized_rank[i] = rank_i / (N_i + 1)   if contributor entered spec i
                     = 1.0                    if contributor did not enter spec i

  rank_i = contributor's rank on spec i (1 = best)
  N_i    = number of contributors who entered spec i
```

**Properties:**
- Range: (0, 1]. A perfect generalist sweeping all 45 specs → near 0; no entries → 1.0.
- Metric-agnostic: `deflection_mm`, `stiffness_to_weight`, and `mass_grams` are treated identically regardless of scale.
- Solo entries: a contributor alone on a spec gets `normalized_rank = 0.5` (not 0.0 — competition is required to prove best-in-class).
- Breadth beats depth: a mediocre agent covering all 45 specs outranks a specialist dominating 3 specs.

### Example

| Scenario | Specs entered | Avg rank per entered spec | overall_score |
|---|---|---|---|
| Perfect generalist (rank 1 of 10 on all 45) | 45 | 1 | 45 × (1/11) / 45 = 0.091 |
| Mediocre generalist (rank 5 of 10 on all 45) | 45 | 5 | 45 × (5/11) / 45 = 0.455 |
| Perfect specialist (rank 1 of 10 on 3 specs) | 3 | 1 | (3 × 1/11 + 42 × 1.0) / 45 = 0.940 |

The perfect specialist (0.940) loses to the mediocre generalist (0.455) — by design.

### Gittensor reward connection

Gittensor rewards the contributor holding the top `overall_score` with the repository's contributor emission share. This ensures mining rewards track *generalist structural engineering skill*, not submission volume or narrow overfitting.

## Determinism check

The first spec in the eval pool is run **twice** with identical inputs. If the two runs produce different scores, the submission is flagged as non-deterministic and rejected. Remaining specs run once — full triple-checking of each spec is too slow given 3 specs per PR.

## Extending the benchmark

When a round's specs are nearly saturated (scores converge within ~1% across competitors), a new round is opened with a different optimization axis or geometry family. The `scripts/rotate_round.py` tool handles round rotation and spec generation.
