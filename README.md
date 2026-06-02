# Forge

**Competitive parametric CAD design — minimize mass, survive the load.**

Forge is a [Gittensor](https://gittensor.io) optimization repository on subnet 74. Miners compete to design the lightest 3D-printable part that passes structural (FEA) validation under a specified load. The miner holding the lowest mass score earns the contributor share of emissions.

This is the kind of problem Autodesk Fusion's Generative Design and nTopology solve with proprietary software and expensive compute. Here you solve it openly, iteratively, and competitively.

---

## The competition

Each **spec** defines a structural challenge:

```json
{
  "material": "pla",
  "load_newtons": 392.4,
  "safety_factor": 2.0,
  "bolt_pattern_mm": [[0,0],[60,0],[60,60],[0,60]],
  "build_volume_mm": [150, 100, 100],
  "max_overhang_deg": 45.0
}
```

Your agent takes the spec and outputs a STEP file. The eval harness:

1. Validates geometry (build volume, bolt holes, overhang, wall thickness)
2. Runs FEA with CalculiX — part must survive `load × safety_factor`
3. Scores the part: **mass in grams** (lower wins)

The current SOTA and leaderboard are in [`sota/score.json`](sota/score.json).

---

## Quick start

See **[QUICKSTART.md](QUICKSTART.md)** for the full walkthrough — clone to first submission in 15 minutes.

```bash
git clone https://github.com/PunchTheDev/forge
cd forge
pip install -e .
forge check-deps

# Test the baseline locally
forge eval agents/baseline/agent.py

# Copy the template and start building
cp -r agents/template agents/<your-name>
# edit agents/<your-name>/agent.py
forge eval agents/<your-name>/agent.py
```

---

## Submitting

1. Fork this repo.
2. Create `agents/<your-name>/agent.py` with a `generate(spec: dict) -> bytes` function.
3. Open a PR. CI runs the eval automatically and posts your score.
4. If you beat the SOTA, a maintainer merges your PR and updates `sota/score.json`.

See [CONTRIBUTING.md](CONTRIBUTING.md) for full submission guidelines.

---

## Agent interface

```python
# agents/<your-name>/agent.py

def generate(spec: dict) -> bytes:
    """
    Given a spec dict, return STEP file bytes for the designed part.

    Constraints are in spec['constraints']. Material is spec['material'].
    The part must pass FEA before mass is scored.

    Time limit: 60 seconds
    Memory limit: 4 GB
    No network access inside sandbox.
    """
    ...
```

The agent may use any Python library available in the eval container (`build123d`, `gmsh`, `numpy`, `scipy`). It may not access the network or call external APIs during evaluation.

---

## Eval stack

| Component | Role |
|---|---|
| [build123d](https://build123d.readthedocs.io) | CAD geometry, STEP import/export |
| [gmsh](https://gmsh.info) | Tetrahedral meshing |
| [CalculiX](https://www.calculix.de) | Linear static FEA solver |
| Docker | Reproducible, isolated eval environment |
| GitHub Actions | CI — scores every PR automatically |

All CPU. No GPU. Eval completes in under 2 minutes.

---

## Docs

- [Scoring](docs/scoring.md) — full scoring pipeline and constraint details
- [Anti-gaming](docs/anti-gaming.md) — threat model and mitigations
- [Hyperparameters](docs/hyperparameters.md) — Gittensor emission configuration

---

## Active specs

| ID | Name | Material | Load | Baseline |
|---|---|---|---|---|
| [001](specs/001_bracket.json) | Wall Mounting Bracket | PLA | 40 kg @ 100 mm | 180 g |
| [002](specs/002_equipment_mount.json) | Industrial Equipment Mount | Aluminum 6061-T6 | 100 kg @ 120 mm | 380 g |
| [003](specs/003_pipe_clamp_bracket.json) | Stainless Steel Pipe-Clamp Bracket | Stainless 316 | 100 kg @ 150 mm | 1500 g |

## Current SOTA

| Spec | Score | Agent | FEA Stress |
|---|---|---|---|
| 001 Wall Bracket | **108.48 g** | slim-spine | 7.50 / 25.0 MPa |
| 002 Equipment Mount | 380.0 g | baseline_aluminum | — |
| 003 Pipe-Clamp Bracket | 1500.0 g | baseline_steel | — |

---

## License

MIT
