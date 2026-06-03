# Contributing to Forge

Forge is a competitive optimization benchmark. Contributions that set a new SOTA earn Gittensor emissions on subnet 74.

## How to submit

### 1. Fork and clone

```bash
gh repo fork PunchTheDev/forge --clone
cd forge
pip install -e .
```

### 2. Create your agent

```bash
forge new agents/<your-name>
```

This scaffolds `agents/<your-name>/agent.py` from the template. Implement the `generate` function:

```python
from forge.sdk.llm import LLMClient

def generate(spec: dict, llm: LLMClient) -> bytes:
    """Return STEP file bytes. Use the LLM to reason about geometry."""
    ...
```

The harness injects `LLMClient` — no API key required. Whitelisted models: `claude-haiku-4-5`, `claude-3-5-haiku`, `gpt-4o-mini`. Both parameters are required; agents that omit `llm` are rejected at eval time.

Starting point in `examples/`:
- `metric-aware-agent/` — adapts strategy per scoring metric, call `llm.chat()` to reason about geometry

The agent runs inside a Docker container:
- **Time:** 60 seconds | **Memory:** 4 GB | **Network:** enabled (LLM calls only)
- **Libraries:** `build123d`, `gmsh`, `numpy`, `scipy`, `OCP`, `httpx`

### 3. Test locally

```bash
# Evaluate on a specific spec
forge eval agents/<your-name>/agent.py --spec r01_001_easy

# Evaluate across an entire round
forge eval agents/<your-name>/agent.py --round round_001
```

Your agent must pass all geometry and FEA checks before opening a PR.

### 4. Open a PR

```bash
git checkout -b <your-name>/bracket-agent
git add agents/<your-name>/
git commit -m "Add <your-name> bracket agent"
git push origin <your-name>/bracket-agent
gh pr create --title "<your-name>: bracket agent"
```

CI automatically evaluates your agent on one randomly-sampled spec from each of the three active rounds and posts a score comment on the PR.

### 5. Beating SOTA

If your submission beats the current leader on any spec (by the required margin), the PR receives the `optimization` label and earns Gittensor emissions upon merge. The marginal-gain requirement decays over time — older SOTAs are easier to displace.

Check the live leaderboard: http://143.244.191.193:8080

---

## What the CI does

1. **Source similarity check** — agents that are near-copies of reference agents are rejected before eval runs.
2. **Geometry checks** — build volume, bolt clearance, overhang, wall thickness.
3. **FEA** — CalculiX linear statics. Part must survive `load × safety_factor`.
4. **Score** — compared against baseline and current SOTA per spec.
5. **Label** — `optimization` (SOTA beater) or `passed` (valid but didn't beat SOTA).

---

## Scoring across all three categories

The competition has three active rounds, each optimizing a different structural metric:

| Round | Metric | Direction |
|---|---|---|
| round_001 | `mass_grams` | minimize |
| round_002 | `stiffness_to_weight` (N/(mm·g)) | maximize |
| round_003 | `deflection_mm` | minimize |

Every PR is evaluated on one spec from each round. A generalist agent that performs well across all three categories ranks highest overall.

---

## Code standards

- No `_private` prefixes — use language-idiomatic privacy.
- Keep agents self-contained in their directory — no cross-agent imports.
- Comments only where the logic isn't self-evident.

---

## Questions

Open an issue. Maintainers respond to genuine questions about the eval harness or spec interpretation.
