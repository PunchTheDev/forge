# Quickstart — Submit to Forge in 15 Minutes

Forge is a competitive CAD optimization benchmark. You submit an `agent.py` that generates a lightweight structural part as a STEP file. The lightest passing design wins.

---

## Prerequisites

You need Python 3.11+, Docker, and Git.

```bash
# Verify Docker is running
docker info

# Clone the repo
git clone https://github.com/PunchTheDev/forge.git
cd forge
```

---

## Step 1 — Check dependencies

```bash
pip install -e .
forge check-deps
```

Install anything missing. The full eval runs inside Docker, but the CLI check confirms the host toolchain is reachable.

---

## Step 2 — Run the baseline locally

```bash
forge eval agents/baseline/agent.py
```

This runs the same pipeline as CI: geometry checks → FEA → mass score. You should see something like:

```
 passed:  True
 mass:    165.20 g   (SOTA: 108.48 g)
 stress:  18.4 / 25.0 MPa
 beats:   False
```

If it fails, run `forge check-deps` and fix the missing tool.

---

## Step 3 — Create your agent

Copy the template:

```bash
cp -r agents/template agents/<your-name>
```

Edit `agents/<your-name>/agent.py`. The only contract:

```python
def generate(spec: dict) -> bytes:
    """Return STEP file bytes for the given spec."""
    ...
```

The `spec` dict contains the full problem constraints (load, bolt pattern, build volume, material). Read `specs/001_bracket.json` to understand the shape.

---

## Step 4 — Test locally until you beat SOTA

```bash
forge eval agents/<your-name>/agent.py
```

Iterate until `beats: True`. The current SOTA is **108.48 g**. Your design must:

- Fit inside the build volume
- Clear all bolt holes
- Survive the FEA load case (von Mises stress < allowable)
- Pass the overhang and wall-thickness geometry checks

See [docs/scoring.md](docs/scoring.md) for the full criteria.

---

## Step 5 — Submit a PR

1. Fork `PunchTheDev/forge` on GitHub.
2. Push your agent folder to a branch on your fork.
3. Open a PR targeting `main`.

CI will run the eval automatically. A score comment appears on your PR within ~10 minutes. If you beat the SOTA, a maintainer reviews and merges — and you hold the leaderboard position until someone else beats you.

---

## Scoring recap

| Criterion | Threshold |
|---|---|
| Build volume | Must fit entirely |
| Bolt holes | ≥ bolt_diameter_clearance_mm clearance around each hole |
| Wall thickness | ≥ 3 mm throughout |
| Overhang | ≤ 45° from vertical (printability) |
| FEA stress | von Mises < material yield / safety_factor |
| **Score** | **Mass in grams — lower is better, no ceiling** |

---

## Tips

- Start from `agents/slim-spine/agent.py` (current SOTA) as a reference — see where material was removed and where it can't be.
- Use `build123d` for clean parametric geometry. Raw OCP also works (see `agents/baseline/`).
- The FEA mesh is C3D4 linear tets at `~2 mm` characteristic length. Features smaller than 3 mm tend to create degenerate mesh elements and fail.
- Non-deterministic designs (randomized without a fixed seed) will fail the 3× determinism check in CI.
- Use a fixed `random.seed(42)` or equivalent if your agent uses any randomness.

---

## Getting help

- [CONTRIBUTING.md](CONTRIBUTING.md) — full contribution guide
- [docs/scoring.md](docs/scoring.md) — scoring and FEA details
- [docs/anti-gaming.md](docs/anti-gaming.md) — what's out of bounds
- Open an issue for anything broken or unclear.
