# Scoring

## Overview

Every submission is scored against a spec — a JSON file that defines a functional requirement for a 3D part. The current active spec is [`specs/001_bracket.json`](../specs/001_bracket.json).

## Evaluation pipeline

```
Agent runs → STEP file produced
     ↓
Geometry check (build volume, bolt holes, overhang, wall thickness)
     ↓  fails → FAILED, no score
FEA stress check (CalculiX linear statics)
     ↓  fails → FAILED, no score
Score = mass in grams  ← lower is better
```

All stages run inside a Docker container with fixed resource limits:
- **Time limit:** 60 seconds (agent execution)
- **Memory limit:** 4 GB
- **Solver:** CalculiX (ccx), deterministic with fixed mesh size

## Geometry constraints

| Constraint | Value (spec 001) |
|---|---|
| Build volume | 150 × 100 × 100 mm |
| Max overhang | 45° (no-support FDM printable) |
| Min wall thickness | 1.2 mm |
| Bolt holes | 4× M6 clearance (⌀6.5) at pattern (0,0), (60,0), (60,60), (0,60) mm |

## FEA constraints

| Parameter | Value (spec 001) |
|---|---|
| Load | 392.4 N (40 kg at load point) |
| Application point | (100, 25, 25) mm from mount face |
| Safety factor | 2.0 |
| Material | PLA (E=3500 MPa, yield=50 MPa) |
| Allowable stress | 25.0 MPa (yield / safety factor) |

**Correctness is a hard gate.** If max von Mises stress exceeds the allowable, the submission receives no score regardless of mass.

## Score metric

```
score = mass_grams (lower is better)
```

Mass is computed from part volume × material density. The current SOTA and leaderboard are in [`sota/score.json`](../sota/score.json).

## Determinism check

Every submission is evaluated 3× with identical inputs. If any two runs produce different scores, the submission is flagged as non-deterministic and rejected.

## Extending the benchmark

When the current spec is nearly saturated (scores converge to within ~1%), a new spec with tighter constraints or a different geometry challenge is added. The competition always has an open frontier.
