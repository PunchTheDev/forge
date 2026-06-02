# Changelog

All notable changes to Forge are recorded here.
Format: newest entries first.

---

## [Unreleased]

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
