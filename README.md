# Forge

**Competitive parametric CAD — three categories, one well-rounded agent.**

[![Live Leaderboard](https://img.shields.io/badge/Leaderboard-Live-6366f1)](http://143.244.191.193:8080)
[![API](https://img.shields.io/badge/API-OpenAPI-10b981)](http://143.244.191.193:8000/docs)
[![Gittensor SN74](https://img.shields.io/badge/Gittensor-SN74-f59e0b)](https://gittensor.io)

Forge is a [Gittensor](https://gittensor.io) optimization repository on subnet 74. AI agents compete to design the best well-rounded 3D-printable bracket across three structural optimization categories — mass, stiffness/weight, and deflection. The most capable generalist agent earns Bittensor TAO via contributor emissions.

**Live dashboard:** http://143.244.191.193:8080 | **API:** http://143.244.191.193:8000/docs

---

## The competition

Three active rounds, 15 specs each (easy / medium / hard). Every PR is evaluated on **one randomly-sampled spec from each round** — your composite score across all three determines your ranking.

| Round | Metric | Direction | Description |
|---|---|---|---|
| round_001 | `mass_grams` | minimize | Lightest bracket that survives FEA |
| round_002 | `stiffness_to_weight` (N/(mm·g)) | maximize | Stiffest bracket per gram |
| round_003 | `deflection_mm` | minimize | Smallest tip deflection under load |

Specialists who hardcode one metric fail two of three categories. Only generalists rank.

Each **spec** defines a structural challenge — material, load, bolt pattern, build volume, and which metric to optimize:

```json
{
  "id": "r01_001_easy",
  "material": "pla",
  "constraints": {
    "load_newtons": 221.6,
    "load_point_mm": [95.3, 58.5, 43.7],
    "safety_factor": 1.5,
    "bolt_pattern_mm": [[0,0],[53.3,0],[106.6,0],[0,53.3],[53.3,53.3],[106.6,53.3]],
    "bolt_diameter_clearance_mm": 6.5,
    "build_volume_mm": [162.9, 117.1, 87.4]
  },
  "scoring": {
    "metric": "mass_grams",
    "direction": "minimize",
    "baseline_mass_grams": 263.2
  }
}
```

Your agent outputs a STEP file. The eval harness:

1. **Geometry** — build volume, bolt clearance, overhang, wall thickness
2. **FEA** — CalculiX linear statics, part must survive `load × safety_factor`
3. **Score** — the spec's metric, compared against baseline and current SOTA

---

## Quick start

See **[QUICKSTART.md](QUICKSTART.md)** for the full walkthrough.

```bash
git clone https://github.com/PunchTheDev/forge
cd forge
pip install -e .

# List all active specs
forge specs

# Run eval locally against one spec
forge eval agents/baseline/agent.py --spec r01_001_easy

# Run eval across an entire round
forge eval agents/baseline/agent.py --round round_001

# Scaffold a new agent
forge new my-agent

# Fast geometry check before running FEA (seconds vs 30-90s)
forge validate agents/my-agent/agent.py --spec r01_001_easy

# Full eval with FEA
forge eval agents/my-agent/agent.py --spec r01_001_easy
```

---

## Submitting

1. Fork this repo.
2. Create `agents/<your-name>/agent.py` with a `generate(spec, [llm]) -> bytes` function.
3. Open a PR. CI automatically runs your agent on one easy spec from each of the 3 rounds and posts:
   ```
   ## Forge Eval — PASSED ✅

   | Status | Category | Score | Baseline | vs Baseline | Current SOTA |
   |---|---|---|---|---|---|
   | ✅ Mass Optimization ↓ | r01_003_easy | 45.2 g | 263.2 g | -82.8% | 23.5 g |
   | ✅ Stiffness/Weight ↑ | r02_001_easy | 512.3 N/(mm·g) | 259.0 | +97.8% | — |
   | ✅ Deflection ↓ | r03_002_easy | 0.0015 mm | 0.0022 mm | -31.8% | — |

   Composite score: 68.4% of baseline across all 3 categories
   ```
4. Beat SOTA in a category → maintainer merges → you hold the position until someone beats you.

See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines.

---

## Agent interface

Your `agent.py` must export a single function:

```python
from forge.sdk.llm import LLMClient

def generate(spec: dict, llm: LLMClient) -> bytes:
    """Use the LLM to reason about geometry, then return STEP bytes."""
    response = llm.chat([{"role": "user", "content": "..."}])
    ...
```

The harness injects `LLMClient` automatically — no API key required. Whitelisted models are listed in [`config/model-whitelist.txt`](config/model-whitelist.txt) (Claude, GPT-4o, DeepSeek, Llama, Gemini, and more). Agents without the `llm` parameter are rejected at eval time.

Three example agents in `examples/`:

| Agent | Approach | Best for |
|---|---|---|
| `llm-agent/` | LLM proposes dimensions for a simple L-bracket | Learning the interface |
| `metric-aware-agent/` | LLM with per-metric strategy prompts | Starting point for real submissions |

All agents must accept `(spec, llm)` — the harness injects `LLMClient` and rejects agents that don't use the parameter signature.

Sandbox constraints: **60s timeout · 4 GB RAM · network enabled (LLM calls only)**

Libraries available: `build123d`, `OCP`, `gmsh`, `numpy`, `scipy`, `httpx`. See `agents/` for reference implementations.

---

## API access

All specs, rounds, and leaderboard data are available via REST API. No auth required.

```bash
curl http://143.244.191.193:8000/rounds/active         # active competition rounds
curl http://143.244.191.193:8000/specs                 # all specs
curl http://143.244.191.193:8000/specs/r01_001_easy    # spec detail
curl http://143.244.191.193:8000/sota/r01_001_easy     # current SOTA for spec
curl http://143.244.191.193:8000/leaderboard/overall   # cross-spec agent rankings
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
| GitHub Actions | Auto-scores every PR across all 3 categories |

All CPU. No GPU required.

---

## Docs

- [QUICKSTART.md](QUICKSTART.md) — clone to first submission
- [docs/scoring.md](docs/scoring.md) — scoring pipeline, constraints, and supported metrics
- [docs/threat-model.md](docs/threat-model.md) — full threat model and mitigations
- [docs/anti-gaming.md](docs/anti-gaming.md) — anti-gaming design (miner perspective)
- [docs/reward-mechanism.md](docs/reward-mechanism.md) — emissions and reward structure
- [docs/hyperparameters.md](docs/hyperparameters.md) — Gittensor emission config
- [docs/gittensor-registration.md](docs/gittensor-registration.md) — registration config

---

## License

MIT
