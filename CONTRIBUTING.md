# Contributing to Forge

Forge is a competitive optimization benchmark. Contributions that set a new SOTA earn Gittensor emissions.

## How to submit

### 1. Fork and clone

```bash
gh repo fork PunchTheDev/forge --clone
cd forge
```

### 2. Create your agent

```bash
mkdir agents/<your-name>
touch agents/<your-name>/agent.py
```

Implement the `generate` function. There are two supported signatures:

**Static agent** (no LLM — backward compatible):
```python
def generate(spec: dict) -> bytes:
    """Return STEP file bytes for a part that satisfies spec."""
    ...
```

**LLM agent** (recommended):
```python
from forge.sdk.llm import LLMClient

def generate(spec: dict, llm: LLMClient) -> bytes:
    """Return STEP file bytes, using the LLM to reason about geometry."""
    ...
```

The harness detects which signature you use via `inspect.signature` and injects
an `LLMClient` automatically — you do not need to provide an API key.

#### Using the LLM client

`LLMClient` wraps the OpenRouter API:

```python
response: str = llm.chat(
    messages=[{"role": "user", "content": "Your prompt here"}],
    max_tokens=512,
)
```

The model is chosen by the harness via `FORGE_MODEL`. During CI, only
whitelisted models are accepted:

- `anthropic/claude-haiku-4-5`
- `anthropic/claude-3-5-haiku`
- `openai/gpt-4o-mini`

Miners do not configure the API key or model — the harness injects both.

#### Observe → Plan → Act pattern

```python
from forge.sdk.llm import LLMClient
import json

def generate(spec: dict, llm: LLMClient) -> bytes:
    # Observe: extract constraints
    c = spec["constraints"]

    # Plan: ask the LLM to reason about geometry parameters
    raw = llm.chat([{
        "role": "user",
        "content": f"Given build volume {c['build_volume_mm']}, propose arm_length and wall_thickness as JSON."
    }])
    dims = json.loads(raw)

    # Act: build the geometry with build123d
    from build123d import Box, BuildPart
    with BuildPart() as part:
        Box(dims["arm_length"], dims["wall_thickness"], dims["wall_thickness"])

    # ... export to STEP and return bytes
```

See `agents/example-llm/agent.py` for a complete working example.

The agent runs inside a Docker container with these constraints:
- **Time:** 60 seconds
- **Memory:** 4 GB
- **Network:** enabled (required for LLM API calls)
- **Libraries available:** `build123d`, `gmsh`, `numpy`, `scipy`, `OCP`, `httpx`

### 3. Test locally

```bash
docker build -t forge-eval .
docker run --rm -v $(pwd):/forge forge-eval \
  --agent /forge/agents/<your-name>/agent.py \
  --spec /forge/specs/001_bracket.json
```

Your agent must output `PASSED` before opening a PR.

### 4. Open a PR

```bash
git checkout -b <your-name>/spec-001
git add agents/<your-name>/
git commit -m "Add <your-name> bracket agent"
git push origin <your-name>/spec-001
gh pr create --title "<your-name>: spec 001, <X> g"
```

CI runs three deterministic eval rounds and posts your score as a comment.

### 5. Beating the SOTA

If your score beats [`sota/score.json`](sota/score.json), a maintainer will:
1. Verify the result manually.
2. Merge the PR.
3. Update `sota/score.json` with your score and contributor name.

You begin earning contributor emissions from that point.

---

## What counts as beating SOTA

- Your mass score must be strictly less than the current SOTA.
- All geometry and FEA constraints must pass.
- All three determinism runs must produce the same score.

Minor improvements (< 0.1 g) may be held for batching to reduce churn.

---

## Design guidance

The current SOTA is a naive L-bracket at ~165 g. The material's allowable stress is 25 MPa (PLA yield / safety factor 2). There is substantial room for improvement through:

- **Topology optimization** — remove material from low-stress regions
- **Ribbed/truss structures** — maintain stiffness while reducing bulk
- **Shell designs** — thin-walled geometries with strategic reinforcement
- **Lattice infill** — if treated as a continuous medium in FEA

The load application point (100 mm from the mount face) and the bolt pattern define where stress concentrations occur. Start there.

---

## Code standards

- No `_private` prefixes on names — use language idioms for scope.
- Keep agents self-contained in their directory — no cross-agent imports.
- Comments only where the logic isn't obvious.

---

## Questions

Open an issue. Maintainers respond to genuine questions about the eval harness or spec interpretation.
