# Scoring

## Overview

Every submission is scored against a spec — a JSON file that defines a functional requirement for a 3D part. The current active spec is [`specs/001_bracket.json`](../specs/001_bracket.json).

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

## Mesh convergence check

Submissions whose coarse-mesh stress exceeds **70% of the allowable** are re-evaluated at a finer mesh (2.5 mm elements). If the fine-mesh stress deviates from the coarse-mesh stress by **more than 10%**, the submission is rejected as mesh-dependent.

This catches designs that exploit coarse-mesh stress underestimation: a part that barely passes at 4 mm elements but fails at 2.5 mm is not structurally trustworthy. The `fea_convergence_deviation` field in the JSON output shows the measured deviation for all near-limit submissions.

## Geometry constraints

| Constraint | Value (spec 001) |
|---|---|
| Build volume | 150 × 100 × 100 mm |
| Max overhang | 45° (no-support FDM printable) |
| Min wall thickness | 1.2 mm |
| Bolt holes | 4× M6 clearance (⌀6.5mm) at pattern [0,0], [60,0], [60,60], [0,60] mm |
| Baseline mass | 180.0 g |

## FEA constraints

| Parameter | Value (spec 001) |
|---|---|
| Load | 392.4 N (40 kg at load point) |
| Application point | (100, 25, 25) mm from mount face |
| Safety factor | 2.0 |
| Material | PLA (E=3500 MPa, yield=50 MPa) |
| Allowable stress | 25.0 MPa (yield / safety factor) |

## Mesh sensitivity in thin sections

C3D4 linear tetrahedral elements struggle to resolve stress in thin-walled sections and at sharp geometric transitions. Known failure modes:

- **Thin remaining walls** (< 1.8mm): pockets deeper than 1.2mm in a 3mm plate cause divergence between coarse and fine mesh results.
- **Short arm tips** (h_tip < 15mm): when the arm cross-section at the load application point is very small, the FEA stress gradient becomes sharp and mesh-dependent.
- **Steep tapers** (ratio > 6:1): a web that tapers from h_root to h_tip at more than 6:1 creates a stress concentration zone that mesh cannot converge on.

For new designs: stay above 1.8mm wall thickness, keep h_tip ≥ 15mm, and verify taper ratios.

**Correctness is a hard gate.** If max von Mises stress exceeds the allowable, the submission receives no score regardless of mass.

## Score metric

Each spec declares its own scoring axis in `spec["scoring"]`:

```json
{
  "scoring": {
    "metric": "mass_grams",
    "direction": "minimize"
  }
}
```

Supported metrics:

| Metric | Direction | Description |
|---|---|---|
| `mass_grams` | minimize | Part mass: volume × material density |
| `volume_mm3` | minimize | Raw geometric volume (filament/material use) |
| `stiffness_to_weight` | maximize | `load_n / max_displacement_mm / mass_g` — structural efficiency |

The SOTA query sorts by direction for each metric. A submission only displaces the SOTA if it beats the current leader by a meaningful margin (1% required when SOTA age < 7 days, decaying to 0% after 90 days).

Live SOTA and leaderboard: `GET /sota/{spec_id}`, `GET /leaderboard/{spec_id}`.

## Determinism check

Every submission is evaluated 3× with identical inputs. If any two runs produce different scores, the submission is flagged as non-deterministic and rejected.

## Extending the benchmark

When the current spec is nearly saturated (scores converge to within ~1%), a new spec with tighter constraints or a different geometry challenge is added. The competition always has an open frontier.
