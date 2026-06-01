# Forge Backlog

Ordered by priority. Items in **bold** are current focus.

---

## In Progress / Next

- [ ] **CLI (`cli.py`)** — `forge eval`, `forge specs`, `forge leaderboard` — miners test locally before submitting
- [ ] **PR #1 merge** (operator action) — slim-spine SOTA update to main
- [ ] **Gittensor registration** (operator action, last step after polish)

---

## Product Surfaces

### CLI
- [ ] `forge eval <agent> [--spec <id>] [--all-specs]` — local eval with same pipeline as CI
- [ ] `forge specs` — list available problem specs with difficulty tier
- [ ] `forge leaderboard` — current SOTA table from `sota/`
- [ ] `forge check-deps` — verify CalculiX, gmsh, OCP installed correctly
- [ ] Local/CI parity: same Docker image tag, pinned solver versions, deterministic seeds

### API (separate repo: `forge-api`)
- [ ] REST backend: GET /specs, GET /leaderboard, GET /submissions, POST /scores
- [ ] CLI, dashboard, and CI all read from this as single source of truth
- [ ] WebSocket feed for live submission status
- [ ] Auth: GitHub OAuth for miner identity
- [ ] Hosted on a public endpoint (operator to provide hosting credentials)

### Dashboard (separate repo: `forge-dashboard`)
- [ ] Live leaderboard table — agent name, score, stress, timestamp, GitHub link
- [ ] SOTA-best-over-time chart (line chart, one line per spec)
- [ ] Per-problem breakdown page
- [ ] Submission status / queue view
- [ ] **3D viewer** — interactive STEP viewer (Three.js + OCCT WASM or similar)
- [ ] Hall-of-fame gallery of top submissions with screenshots
- [ ] One-click "reproduce this result" button (links to pinned Docker run command)
- [ ] Shareable — clean URL, good OG tags, no login required to view

---

## Core Benchmark

### 1. Problem Sourcing (anti-saturation engine)
- [ ] Procedural spec generator: parametric bracket/mount/lever arm families
  - Randomized: loads (N), bolt patterns, build envelopes, mass targets
  - Difficulty tiers: Easy (200-300g), Medium (100-200g), Hard (<100g)
  - Seed from real CAD datasets: ABC dataset, DeepCAD, Fusion 360 Gallery
- [ ] Public problem set (local dev, visible): `specs/public/`
- [ ] Held-out private problem set (official scoring): `specs/private/` (not in repo)
- [ ] Problem rotation schedule: refresh ~monthly, announce via Discord

### 2. Trustworthy FEA Oracle
- [ ] Mesh-convergence check: run at 2 mesh densities, flag >5% stress deviation
- [ ] Randomized load-case perturbations: ±10% load magnitude, ±5° direction
- [ ] Reject non-manifold / degenerate geometry before meshing
- [ ] Safety-factor margin reporting (not just pass/fail)
- [ ] Detect thin-shell exploitation (wall < min_wall_thickness throughout)

### 3. Untrusted-Code Security
- [ ] Upgrade sandbox: gVisor (`runsc`) or Firecracker isolation
- [ ] Block network egress during agent eval (no `--network` in docker run)
- [ ] Hard CPU time limit (not wall time) via cgroups
- [ ] Drop all capabilities: `--cap-drop ALL` in docker run
- [ ] Threat model doc: code injection, resource exhaustion, side-channel, exfiltration

### 4. Reproducibility + Rescore Policy
- [ ] Pin Docker image by digest (not tag) in CI
- [ ] Pin CalculiX version, gmsh version, OCP version in Dockerfile
- [ ] Store per-submission: image digest, mesh seed, random seeds
- [ ] `sota/score.json` includes container digest + reproduce command
- [ ] Rescore policy doc: season/epoch model, when old scores get invalidated
- [ ] Dashboard "reproduce" button generates pinned `docker run` command

### 5. Onboarding (target: <15 minutes)
- [ ] `QUICKSTART.md`: clone → check deps → run baseline → get score → submit
- [ ] Starter template agent: `agents/template/agent.py` with TODOs + inline comments
- [ ] Hello-world submission walkthrough in README
- [ ] `forge check-deps` command to validate local environment
- [ ] Estimated time on each quickstart step

### 6. Cost/Spam Controls
- [ ] Hash-cache: skip re-eval if STEP file SHA matches previous submission
- [ ] Per-miner eval budget: max N evals/day (configurable)
- [ ] Queue management: max 1 in-flight eval per miner
- [ ] Similarity check: reject if cosine similarity to current leader STEP > 0.95
- [ ] PR spam detection: flag PRs with identical agent code, different author

### 7. Anti-Gaming Hardening
- [ ] Private eval before reveal: hash commitment scheme (miner submits hash first)
- [ ] Held-out test set rotation: swap eval spec monthly
- [ ] Reward decay: score bonus decays 50% every 14 days (hyperparameter)
- [ ] Plagiarism check: STEP file geometric similarity vs all prior submissions
- [ ] Rate limiting: max 3 PR submissions per miner per week

---

## Agents (SOTA chase)
- [ ] Run baseline + ribbed agents through FEA to get real masses (after PR #1 merge)
- [ ] Topology-optimized truss agent (SIMP/OC method, target <80g)
- [ ] Lattice infill agent (gyroid/kagome structure)
- [ ] Shell-FEM optimized agent (thin walls at stress concentration points)
- [ ] Agent README: document each design's reasoning and measured score

---

## Hygiene
- [ ] `.github/ISSUE_TEMPLATE/` — bug report + feature request templates
- [ ] `CHANGELOG.md` — version history
- [ ] Pre-commit hooks: black, ruff, mypy for benchmark/ code
- [ ] Semantic versioning for benchmark: break on geometry/FEA algorithm change = major bump
