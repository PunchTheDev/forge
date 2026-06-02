# Quickstart — Submit to Forge in 15 Minutes

Forge is a competitive parametric CAD benchmark on Gittensor SN74. Submit an `agent.py` that generates a lightweight 3D-printable structural part as a STEP file. The lightest design that survives finite element analysis holds the SOTA and earns contributor emissions.

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

## Step 1 — Understand the spec

Each problem is a JSON file in `specs/`. The bracket spec:

```json
{
  "id": "001_bracket",
  "version": "1.0",
  "material": "pla",
  "constraints": {
    "load_newtons": 392.4,
    "load_point_mm": [100, 25, 25],
    "safety_factor": 2.0,
    "bolt_pattern_mm": [[0,0],[60,0],[60,60],[0,60]],
    "bolt_diameter_clearance_mm": 6.5,
    "build_volume_mm": [150, 100, 100],
    "max_overhang_deg": 45.0,
    "min_wall_thickness_mm": 1.2
  },
  "scoring": {
    "metric": "mass_grams",
    "direction": "minimize",
    "baseline_mass_grams": 180.0
  }
}
```

Retrieve any spec from the API:
```bash
curl http://143.244.191.193:8000/specs/001_bracket
```

---

## Step 2 — Create your agent

```bash
cp -r agents/template agents/<your-name>
```

Edit `agents/<your-name>/agent.py`. Two supported signatures:

**Static agent** (no LLM):
```python
def generate(spec: dict) -> bytes:
    """Takes the spec dict, returns STEP file bytes."""
    ...
```

**LLM agent** (recommended — harness injects the client):
```python
from forge.sdk.llm import LLMClient

def generate(spec: dict, llm: LLMClient) -> bytes:
    """Use the LLM to reason about geometry, then return STEP bytes."""
    response = llm.chat([{"role": "user", "content": "..."}])
    ...
```

No API key needed — the harness injects `LLMClient` automatically using whitelisted models. See `examples/llm-agent/agent.py` for a complete working example.

Reference implementations in `agents/`:
- `taper-beam/` — clean I-beam (~38g)
- `lean-arm/` — I-beam baseline (~32g)
- `compact-arm/` — pocketed arm approach

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
forge eval agents/<your-name>/agent.py --spec specs/round_001/r01_001_easy.json
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
forge eval agents/<your-name>/agent.py
```

Output:
```
 spec:    001_bracket — Wall Mounting Bracket
 passed:  True
 mass:    28.40 g   (SOTA: 29.15 g)
 stress:  22.1 / 25.0 MPa
 beats:   True  ← you're in the lead
```

Iterate until `beats: True`. Design constraints:
- Fits inside the build volume (150 × 100 × 100 mm)
- All bolt holes clear by `bolt_diameter_clearance_mm`
- Wall thickness ≥ `min_wall_thickness_mm` throughout (1.2mm for bracket spec)
- Overhang ≤ 45° (printable without supports)
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
# List all problem specs
curl http://143.244.191.193:8000/specs

# Get a specific spec
curl http://143.244.191.193:8000/specs/001_bracket

# Current SOTA for a spec
curl http://143.244.191.193:8000/sota/001_bracket

# Full leaderboard for a spec
curl http://143.244.191.193:8000/leaderboard/001_bracket

# All-time cross-spec rankings
curl http://143.244.191.193:8000/leaderboard/overall
```

Interactive docs: http://143.244.191.193:8000/docs

---

## Tips for agents and LLMs

- **Start from `agents/compact-arm/agent.py`** — current verified SOTA at 27.22g. Understand every dimension.
- **The hard constraint is FEA**: geometry checks are easy to satisfy; passing FEA with acceptable mesh convergence is the real challenge.
- **Minimum wall = 2–3 mm**: C3D4 linear tets fail to resolve stress in walls thinner than 2 mm.
- **Determinism is required**: if your design uses randomness, fix `random.seed(42)`. CI runs 3× and all scores must match.
- **AP214IS STEP schema**: always set `Interface_Static.SetCVal_s("write.step.schema", "AP214IS")` before writing STEP. AP203 causes SIGSEGV on complex geometry.
- **Use build123d**: cleaner parametric API than raw OCP. See `agents/taper-beam/` for an OCP example.
- **Progressive improvement beats one-shot guessing**: 108g → 56g → 38g → 32g was achieved by understanding where material is structurally necessary.

---

## CLI reference

```
forge eval <agent.py>              # benchmark an agent
forge eval <agent.py> --spec 001   # against a specific spec
forge eval <agent.py> --all        # against all public specs
forge eval <agent.py> --json       # JSON output for scripting
forge specs                        # list all available specs
forge leaderboard                  # show current SOTA
forge check-deps                   # verify local toolchain
```

---

## Getting help

- [CONTRIBUTING.md](CONTRIBUTING.md) — full contribution guide
- [docs/scoring.md](docs/scoring.md) — scoring and FEA details
- [docs/anti-gaming.md](docs/anti-gaming.md) — what's out of bounds
- Open a GitHub issue for anything broken or unclear.
