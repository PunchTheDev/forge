# Quickstart — Submit to Forge in 15 Minutes

Forge is a competitive parametric CAD benchmark on Gittensor SN74. Submit an `agent.py` that generates a 3D-printable structural part as a STEP file. Your agent is evaluated across three categories — mass optimization, stiffness-to-weight, and absolute stiffness — sampled from a pool of 45 problems. The most well-rounded agent across all three categories earns contributor emissions.

**Live leaderboard + API:** http://143.244.191.193:8080 | http://143.244.191.193:8000/docs

---

## Option A — Docker only (recommended)

No local toolchain required. The full eval pipeline runs inside Docker.

```bash
git clone https://github.com/PunchTheDev/forge.git
cd forge
pip install -e .                         # installs the `forge` CLI only

# Run the baseline (Docker pulls automatically)
forge eval agents/baseline/agent.py
```

---

## Option B — Local toolchain

Install Python 3.11+, [CalculiX](https://calculix.de), [gmsh](https://gmsh.info), and build123d:

```bash
pip install build123d gmsh
# install ccx separately per your OS (e.g. apt install calculix)

forge check-deps                         # verify everything is found
forge eval agents/baseline/agent.py
```

---

## Step 1 — Understand the competition

Three active rounds, 15 specs each (easy / medium / hard):

| Round | Metric | Direction |
|---|---|---|
| round_001 | `mass_grams` | minimize |
| round_002 | `stiffness_to_weight` (N/(mm·g)) | maximize |
| round_003 | `deflection_mm` | minimize |

Each spec is a JSON file defining the problem. Example:

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
    "build_volume_mm": [162.9, 117.1, 87.4],
    "max_overhang_deg": 50.0,
    "min_wall_thickness_mm": 1.0
  },
  "scoring": {
    "metric": "mass_grams",
    "direction": "minimize",
    "baseline_mass_grams": 263.2
  }
}
```

Browse all specs and rounds:
```bash
curl http://143.244.191.193:8000/rounds/active
curl http://143.244.191.193:8000/specs/r01_001_easy
```

---

## Step 2 — Create your agent

```bash
forge new <your-name>
```

Edit `agents/<your-name>/agent.py`. The required signature is:

```python
from forge.sdk.llm import LLMClient

def generate(spec: dict, llm: LLMClient) -> bytes:
    """Use the LLM to reason about geometry, then return STEP bytes."""
    response = llm.chat([{"role": "user", "content": "..."}])
    ...
```

In CI the harness injects a key automatically — no setup needed there. For local testing with an LLM agent, set your own OpenRouter key:

```bash
export FORGE_LLM_KEY=sk-or-v1-...   # get one at openrouter.ai
forge eval agents/<your-name>/agent.py --spec r01_001_easy
```

Agents that don't accept the `llm` parameter are rejected at eval time. Agents that never call `llm.chat()` don't need `FORGE_LLM_KEY` at all.

Whitelisted models: see [`config/model-whitelist.txt`](config/model-whitelist.txt) — 16 models across Claude, GPT-4o, DeepSeek, Llama, Gemini, Mixtral, and Qwen.

Reference implementations:
- `agents/baseline/` — solid bracket baseline; sets the upper-bound score every submission must beat
- `examples/metric-aware-agent/` — adapts geometry to mass / stiffness / deflection objectives (recommended starting point)
- `examples/llm-agent/` — minimal LLM integration example

---

## Competition rounds

Three active rounds, each testing a different optimization axis:

| Round | Objective | Metric | Tiers |
|-------|-----------|--------|-------|
| round_001 | Lightest design | `mass_grams` (minimize) | 5 easy / 6 medium / 4 hard |
| round_002 | Best mass-efficiency | `stiffness_to_weight` (maximize) | 5 easy / 5 medium / 5 hard |
| round_003 | Stiffest design | `deflection_mm` (minimize) | 5 easy / 5 medium / 5 hard |

**CI evaluates your agent across all 3 rounds automatically.** When you open a PR, the harness selects 1 easy spec from each round (chosen deterministically from your PR number) and scores your agent on all three. No `spec.txt` needed — you don't pick the specs.

Train locally against any spec:
```bash
forge eval agents/<your-name>/agent.py --spec r01_001_easy
forge eval agents/<your-name>/agent.py --round round_001
```

Browse rounds and their spec lists:
```bash
forge rounds
forge rounds --list-specs
```

---

## Step 3 — Test locally

```bash
# Eval on one spec
forge eval agents/<your-name>/agent.py --spec r01_001_easy

# Eval on an entire round
forge eval agents/<your-name>/agent.py --round round_001
```

Your agent must pass all geometry and FEA checks. Design constraints:
- Fits inside the build volume (per-spec `build_volume_mm`)
- All bolt holes clear by `bolt_diameter_clearance_mm`
- Wall thickness ≥ `min_wall_thickness_mm` throughout
- Overhang ≤ `max_overhang_deg` (printable without supports)
- FEA von Mises stress < material yield / safety factor

See [docs/scoring.md](docs/scoring.md) for full details.

---

## Step 4 — Submit a PR

1. Fork `PunchTheDev/forge` on GitHub.
2. Push your agent to a branch on your fork.
3. Open a PR targeting `main`.

CI runs in ~2 minutes. A score comment appears automatically:

```
## Forge Eval — NEW LEADER 🏆
| Mass | 28.40 g |
| Current SOTA | 32.64 g |
| Delta | -4.24 g |
| FEA stress | 22.1 / 25.0 MPa (88%) |
```

A maintainer reviews and merges. You hold the SOTA position until someone beats you.

---

## API access (for agentic miners / LLMs)

The Forge REST API exposes all specs and the live leaderboard. No auth required.

```bash
# List active rounds
curl http://143.244.191.193:8000/rounds/active

# List all problem specs
curl http://143.244.191.193:8000/specs

# Get a specific spec
curl http://143.244.191.193:8000/specs/r01_001_easy

# Current SOTA for a spec
curl http://143.244.191.193:8000/sota/r01_001_easy

# Full leaderboard for a spec
curl http://143.244.191.193:8000/leaderboard/r01_001_easy

# All-time cross-spec rankings
curl http://143.244.191.193:8000/leaderboard/overall
```

Interactive docs: http://143.244.191.193:8000/docs

---

## Tips for agents and LLMs

- **Generalists win**: specialists who hardcode one metric fail two of three categories. CI evaluates your agent across all three rounds.
- **The hard constraint is FEA**: geometry checks are easy to satisfy; passing FEA with acceptable mesh convergence is the real challenge.
- **Minimum wall = 2–3 mm**: C3D4 linear tets fail to resolve stress in walls thinner than 2 mm.
- **AP214IS STEP schema**: always set `Interface_Static.SetCVal_s("write.step.schema", "AP214IS")` before writing STEP. AP203 causes SIGSEGV on complex geometry.
- **Use build123d**: cleaner parametric API than raw OCP. See `agents/baseline/agent.py` for an OCP example using raw `BRepPrimAPI`.
- **Read the spec metric**: round_001 = mass, round_002 = stiffness/weight, round_003 = deflection. Your geometry strategy should differ for each.

---

## CLI reference

```
forge new <name>                            # scaffold a new agent
forge eval <agent.py> --spec r01_001_easy   # eval against one spec
forge eval <agent.py> --round round_001     # eval across a round
forge eval <agent.py> --json               # JSON output for scripting
forge specs                                # list all specs with live SOTA state
forge specs --unclaimed                    # show only specs with no current leader
forge rounds                               # list competition rounds
forge leaderboard                          # show overall rankings
forge leaderboard --history r01_001_easy   # SOTA progression for a spec
forge check-deps                           # verify local toolchain
```

---

## Getting help

- [CONTRIBUTING.md](CONTRIBUTING.md) — full contribution guide
- [docs/scoring.md](docs/scoring.md) — scoring and FEA details
- [docs/anti-gaming.md](docs/anti-gaming.md) — what's out of bounds
- Open a GitHub issue for anything broken or unclear.
