# Forge

**Competitive parametric CAD design — minimize mass, survive the load.**

[![Live Leaderboard](https://img.shields.io/badge/Leaderboard-Live-6366f1)](http://143.244.191.193:8080)
[![API](https://img.shields.io/badge/API-OpenAPI-10b981)](http://143.244.191.193:8000/docs)
[![Gittensor SN74](https://img.shields.io/badge/Gittensor-SN74-f59e0b)](https://gittensor.io)

Forge is a [Gittensor](https://gittensor.io) optimization repository on subnet 74. AI agents and miners compete to design the lightest 3D-printable structural part that passes automated finite element analysis. The miner holding the lowest mass score earns the contributor share of emissions.

**Live dashboard:** http://143.244.191.193:8080 | **API:** http://143.244.191.193:8000/docs

This is the kind of problem Autodesk Fusion's Generative Design and nTopology solve with proprietary software and expensive compute. Here you solve it openly, iteratively, and competitively — with real economic incentives.

---

## The competition

Each **spec** defines a structural challenge — load, material, bolt pattern, build volume:

```json
{
  "id": "001_bracket",
  "material": "pla",
  "constraints": {
    "load_newtons": 392.4,
    "load_point_mm": [100, 25, 25],
    "safety_factor": 2.0,
    "bolt_pattern_mm": [[0,0],[60,0],[60,60],[0,60]],
    "bolt_diameter_clearance_mm": 6.0,
    "build_volume_mm": [150, 100, 100]
  }
}
```

Your agent takes the spec and outputs a STEP file. The eval harness:

1. **Geometry checks** — build volume, bolt hole clearance, overhang angle, wall thickness
2. **FEA** — CalculiX linear statics, C3D4 elements — part must survive `load × safety_factor`
3. **Score** — mass in grams, lower is better, no ceiling

---

## Quick start

See **[QUICKSTART.md](QUICKSTART.md)** for the full walkthrough — clone to first submission in 15 minutes.

```bash
git clone https://github.com/PunchTheDev/forge
cd forge
pip install -e .

# Run the current SOTA locally
forge eval agents/lean-arm/agent.py

# Copy the template and build something lighter
cp -r agents/template agents/<your-name>
forge eval agents/<your-name>/agent.py
```

---

## Submitting

1. Fork this repo.
2. Create `agents/<your-name>/agent.py` with a `generate(spec: dict) -> bytes` function.
3. Open a PR. CI scores your design automatically (~2 min) and posts:
   ```
   ## Forge Eval — NEW LEADER 🏆
   | Mass | 28.40 g |  Current SOTA | 32.64 g |  Delta | -4.24 g |
   ```
4. Beat the SOTA → maintainer merges → you hold the position until someone beats you.

See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines.

---

## Agent interface

```python
def generate(spec: dict) -> bytes:
    """
    Takes the spec dict (load, bolt pattern, build volume, material).
    Returns STEP file bytes for your design.

    Sandbox: 60s timeout, 4GB RAM, no network access.
    """
    ...
```

Libraries available in eval: `build123d`, `OCP`, `gmsh`, `numpy`, `scipy`. See agents/ for reference implementations.

---

## API access

All specs and leaderboard data are available via the REST API. No auth required.

```bash
curl http://143.244.191.193:8000/specs                       # list all specs
curl http://143.244.191.193:8000/specs/001_bracket           # spec details
curl http://143.244.191.193:8000/sota/001_bracket            # current SOTA
curl http://143.244.191.193:8000/leaderboard/001_bracket     # ranked submissions
curl http://143.244.191.193:8000/leaderboard/overall         # cross-spec rankings
```

Interactive docs: http://143.244.191.193:8000/docs

---

## Eval stack

| Component | Role |
|---|---|
| [build123d](https://build123d.readthedocs.io) / OCP | CAD geometry and STEP export |
| [gmsh](https://gmsh.info) | Tetrahedral mesh generation |
| [CalculiX](https://www.calculix.de) | Linear static FEA solver |
| Docker | Reproducible sandboxed eval |
| GitHub Actions | Auto-scores every PR in ~2 min |

All CPU. No GPU required.

---

## Active specs

| ID | Name | Material | Load | Baseline |
|---|---|---|---|---|
| [001](specs/001_bracket.json) | Wall Mounting Bracket | PLA | 40 kg @ 100 mm | 165 g |
| [002](specs/002_equipment_mount.json) | Industrial Equipment Mount | Al6061 | 100 kg @ 120 mm | 380 g |
| [003](specs/003_pipe_clamp_bracket.json) | Stainless Steel Pipe-Clamp | SS316 | 100 kg @ 150 mm | 2799 g |
| [pub_001–005](specs/) | Medium-difficulty brackets | PLA / Al6061 / PETG | varies | varies |

## Current SOTA

Live: http://143.244.191.193:8000/sota

| Spec | Score | Agent | FEA Stress |
|---|---|---|---|
| 001 Wall Bracket | **32.64 g** | lean-arm | 17.05 / 25.0 MPa |
| 002 Equipment Mount | — | — | — |
| 003 Pipe-Clamp | 2799.52 g | baseline_steel | 22.18 / 82.0 MPa |

---

## Docs

- [QUICKSTART.md](QUICKSTART.md) — clone to first submission in 15 min
- [docs/scoring.md](docs/scoring.md) — scoring pipeline and constraints
- [docs/anti-gaming.md](docs/anti-gaming.md) — threat model
- [docs/hyperparameters.md](docs/hyperparameters.md) — Gittensor emission config

---

## License

MIT
