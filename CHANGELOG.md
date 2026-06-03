# Changelog

All notable changes to Forge are recorded here.
Format: newest entries first.

---

## [Unreleased]

## 2026-06-03

### Added
- **Metric-aware example** (`examples/metric-aware-agent/`): reads `spec["scoring"]["metric"]` and sends a tailored geometry strategy to the LLM per category — recommended starting point for new agents.
- **`forge leaderboard --history <spec_id>`**: prints chronological SOTA progression for a spec — date, contributor, score, % improvement per step. Fetches from `/sota/{spec_id}/history`.
- **Multi-spec pool eval in CI** (`scripts/select_eval_specs.py`, `run_eval_pool.py`, `record_submissions.py`): each PR is evaluated on one randomly-sampled easy spec from each of the 3 active rounds (not just round_001). PR comment shows cross-category table + composite score.
- **Per-spec SOTA reference STEPs** (`sota/{spec_id}/reference.step`): geometric similarity check is now per-spec first, falling back to the global reference.

### Fixed
- **CLI metric units in eval output**: `forge eval` verbose output and summary table now use `_fmt_score(score, metric)` instead of hardcoded `g` — round_002 shows `N/(mm·g)`, round_003 shows `mm`.
- **Template agent field names**: docstring corrected — `load_n` → `load_newtons`, `spec["safety_factor"]` → `spec["constraints"]["safety_factor"]`.
- **Unclaimed spec SOTA label**: CI now correctly applies the `optimization` label (2× Gittensor multiplier) when the first miner claims an unclaimed spec. Previously the label was only applied when beating an existing SOTA.

## 2026-06-02

### Added
- **Round 003 — Deflection minimization**: 15 specs (seeds 700/800/900, easy/medium/hard). Objective: minimize `deflection_mm`. High-modulus materials (Al, SS) are decisive.
- `deflection_mm` metric: `evaluate.py`, `generator.py`, CLI `--metric deflection_mm`, `METRIC_CONFIG` in API/dashboard.
- Eval PR comment now shows correct label, unit, and 4-decimal delta for `deflection_mm`; suppresses redundant FEA displacement row.
- **Round 002 — Stiffness-to-weight**: 15 specs (seeds 400/500/600). Objective: maximize `stiffness_to_weight`.
- Gittensor label pipeline: CI applies `optimization`/`passed` labels with marginal-gain eligibility check.
- Threat model doc (`docs/threat-model.md`): 7 attack classes with mitigations and residual risks.
- Thingiverse catalog module (`catalog/`): fetch/theme/ingest pipeline, `forge catalog` CLI command.
- **LLM agent contract**: `generate(spec, llm)` interface, `LLMClient` SDK wrapping OpenRouter, `forge eval --agent` injects whitelisted model. Legacy static interface still supported via signature inspection.
- Whitelisted models: `anthropic/claude-haiku-4-5`, `anthropic/claude-3-5-haiku`, `openai/gpt-4o-mini`.
- Two-density FEA mesh convergence: coarse (4 mm) + fine (2.5 mm), triggered at 70% of allowable stress.
- Procedural spec generator and 5 public medium specs (`pub_001`–`pub_005`).
- GitHub Actions eval CI (`eval.yml`): runs on `agents/**` changes, posts PR comment, records submission to forge-api.
- `--cap-drop ALL --pids-limit 256` sandbox hardening in eval docker run.
- Geometric similarity check against SOTA reference STEP file.
- Deduplication of already-scored commit hashes in CI.
- `QUICKSTART.md`, `.github/ISSUE_TEMPLATE/` (bug report + feature request), `CONTRIBUTING.md`, `VISION.md`.
- `forge` CLI: `forge eval`, `forge spec`, `forge sota`, `forge catalog`.

### Fixed
- Spec path resolution across round subdirectories in CI.
- Flat glob for `cmd_specs`/`status`.
- `spec.txt` routing: each agent dir declares its target spec.

---

## 2026-05-xx (initial scaffold)

### Added
- Scaffold: `benchmark/`, `agents/`, `sota/`, `docs/`, `scripts/`.
- FEA oracle (CalculiX linear statics): correctness gates — build volume, bolt holes, overhang, wall thickness, degenerate mesh rejection, sparse load zone rejection.
- Baseline agent (`agents/baseline/`): solid bracket, establishes upper-bound score.
- `spec-001`, `spec-002`, `spec-003`: parametric bracket specs (Al6061, SS316, PETG).
- Score axes: `mass_grams` (minimize), `stiffness_to_weight` (maximize), `deflection_mm` (minimize).
- Stack: build123d (OCP) + gmsh + CalculiX — CPU-only.
- `Dockerfile` for eval sandbox.
- `docs/hyperparameters.md`: Gittensor hyperparameter mapping for Forge.
- `docs/gittensor-registration.md`: registration config + submission instructions.
