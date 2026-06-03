# Changelog

All notable changes to Forge are recorded here.
Format: newest entries first.

---

## [Unreleased]

## 2026-06-03 (step 216)

### Docs
- **`forge validate` added to README and QUICKSTART** (PR #273): the command existed since PR #261 but was absent from all user-facing docs. README quick-start block now shows `forge validate` before `forge eval`. QUICKSTART Step 3 restructured to lead with the geometry-only check (~5s) before the full FEA run (30-90s). CLI reference table updated.

## 2026-06-03 (step 215)

### Fixed
- **`pytest` testpaths set to `tests/`** (PR #271, `pyproject.toml`): bare `python -m pytest` was auto-discovering `scripts/test_ocp_subprocess.py`, which runs Docker-only subprocess code at module level with `cwd="/forge"`. This caused an immediate collection error on any machine without the Docker container mounted. Added `[tool.pytest.ini_options] testpaths = ["tests"]` so bare `pytest` behaves identically to the CI invocation (`python -m pytest tests/`).

## 2026-06-03 (step 214)

### Changed
- **Model whitelist expanded to Claude 4.6** (PR #268, `config/model-whitelist.txt`): added `anthropic/claude-sonnet-4-6`, `anthropic/claude-opus-4-6`, and `anthropic/claude-haiku-4-5-20251001`. Miners can now use the latest Claude generation in their agents.

## 2026-06-03 (step 212)

### Changed
- **`forge check-deps` Docker-aware output** (PR #267, `cli.py`): reorganized into two sections — "Option A — Docker (recommended)" and "Option B — Native toolchain". Docker path is checked first: reports Docker version and whether `forge-eval:latest` is already cached locally. Native path (ccx/gmsh/OCP) unchanged. Returns success if either Docker or native toolchain is ready, so Docker-only miners no longer get a false failure. Actionable summary line at the bottom directs to the correct eval command for the user's setup.

## 2026-06-03 (step 211)

### Fixed
- **`--json` mode clean output** (PR #265, `cli.py`): `forge eval --json` and `forge validate --json` were printing spec/agent divider headers before the JSON payload, making the output unparseable by `jq` or any JSON consumer. Guarded the per-spec header block with `if not args.json:` in both `cmd_eval` and `cmd_validate`.

## 2026-06-03 (step 210)

### Added
- **`TestGeometryOnly` unit tests** (PR #263, `tests/test_evaluate.py`): 4 tests cover the `geometry_only=True` path in `evaluate()` shipped in PR #261. Verifies FEA is never called in geometry-only mode, score equals geometry mass on pass, geometry failure surfaces correctly, agent errors are reported before geometry. Test count: 58 → 62 passed.

## 2026-06-03 (step 209)

### Added
- **`forge validate` command** (PR #261, `cli.py`, `benchmark/evaluate.py`): geometry-only fast check — runs the agent and validates STEP geometry (build volume, bolt holes, overhang, wall thickness) without running FEA. Returns pass/fail + mass estimate in seconds vs 30-90s for full FEA. Add `--geometry-only` flag to `benchmark.evaluate` for the same path. Usage: `forge validate agents/my-agent/agent.py --spec r01_001_easy`.

## 2026-06-03 (step 206)

### Fixed
- **`forge new` fallback scaffold signature** (PR #259, `cli.py`): when `agents/template/agent.py` is absent, `forge new` generated a one-param scaffold `generate(spec: dict) -> bytes` — rejected by the eval harness. Fixed to `generate(spec: dict, llm: LLMClient) -> bytes` with the required `LLMClient` import. Also fixed f-string interpolation of `{name}` in the docstring (was a raw string).

## 2026-06-03 (step 205)

### Added
- **GHCR pre-built eval image** (PR #257, #258): `publish-image.yml` workflow builds and pushes `ghcr.io/punchthedev/forge-eval:latest` whenever `Dockerfile` or `requirements.txt` change on main. `_ensure_docker_image()` now pulls from GHCR on first use (~1 min download) and falls back to a local build if the pull fails. Saves ~4 min on first `forge eval --docker` run.

### Fixed
- **QUICKSTART.md Option A timing** (PR #258): updated build time claim from "~5 minutes" to "~1 min download" to reflect the GHCR pull path.

## 2026-06-03 (step 204)

### Fixed
- **`--docker` absent from local testing docs** (PR #255): CONTRIBUTING.md and QUICKSTART.md both showed bare `forge eval` in their "Test locally" sections after `--docker` was added in PR #253. Updated both to show `--docker` as the recommended form; bare eval retained as fallback for users with a local toolchain.

## 2026-06-03 (session 15)

### Added
- **`forge eval --docker` flag** (PR #253, `cli.py`): runs the eval pipeline inside the `forge-eval` Docker container — same flags as CI (`--cap-drop ALL`, `--pids-limit 256`, `4g/2cpu`, workspace volume-mount). Builds the image automatically on first use. No local OCP/CalculiX/gmsh installation needed. `_ensure_docker_image()` checks for the image before each run; `_run_evaluate_docker()` implements the Docker path.

### Fixed
- **QUICKSTART.md "Option A" accuracy** (PR #253): previously claimed `forge eval` ran inside Docker, but the CLI used Python directly. Updated to show `forge eval --docker` and correct image-build timing (once, ~5 min).

## 2026-06-03 (session 14)

### Fixed
- **Stale 3-model whitelist in docs and code** (PRs #249, #250, #251): `README.md`, `QUICKSTART.md`, `cli.py`, `scripts/run_eval_pool.py`, `scripts/run_hidden_eval.py`, and `agents/template/agent.py` all referenced the old hardcoded 3-model list instead of `config/model-whitelist.txt`. CLI and scripts now load the file at runtime (falling back to the 3-model list only if the file is absent); docs now link to the file directly.

## 2026-06-03 (session 11)

### Added
- **Geometry unit tests** (PR #244, `tests/test_geometry.py`): 13 tests across three classes covering build-volume pass/fail, wall-thickness enforcement, and `GeometryResult` field correctness. Uses OCC primitive shapes (box, thin plate) constructed in-process — no fixture STEP files needed. Tests skip automatically when OCP is not installed.
- **Framework CI workflow** (PR #244, `.github/workflows/test.yml`): runs `pytest tests/` on every non-agent PR and push to main. Prevents regressions in the benchmark framework code path.

### Fixed
- **Dead `GEOMETRY_AVAILABLE` probe in `test_evaluate.py`** (PR #245): the flag was defined and set but never referenced in any `skipif`; moved to `test_geometry.py` where it belongs.

## 2026-06-03 (session 10)

### Added
- **Thingiverse catalog expansion** (PRs #235, #236, #239, #241): 40 new catalog specs across all three metrics (mass, stiffness, deflection) seeded from Thingiverse via `gh workflow run ingest.yml`. Catalog now holds 65 specs covering easy/medium/hard tiers and four materials.
- **Metric-suffix IDs in catalog ingest** (PR #238, `catalog/ingest.py`): spec IDs are now `th_{thing_id}_{metric_slug}` (e.g. `th_1182945_mass`) so the same Thingiverse thing can have specs for different metrics without filename collisions.

### Fixed
- **CLI leaderboard shows `overall_score` instead of `avg_rank`** (PR #240, `cli.py`): `forge leaderboard` table column updated to match the API and dashboard; `overall_score` (breadth-normalized percentile rank, lower is better) is the primary Gittensor reward metric.

## 2026-06-03 (session 9)

### Security
- **Block eval-code injection via workspace volume mount** (PR #233, `.github/workflows/eval.yml`): a miner could open a PR modifying both `agents/alice/agent.py` and `benchmark/evaluate.py`; since the entire workspace is volume-mounted into the Docker container, their modified eval code would run, enabling arbitrary score fabrication. Added `infra_guard` CI step that rejects any agent PR touching `benchmark/`, `scripts/`, `Dockerfile`, or `.github/` paths.

### Fixed
- **`_parse_frd_stress` fixed-width column parsing** (PR #232, `benchmark/fea.py`): CalculiX `.frd` uses fixed-width E12.5 format; adjacent negative values can concatenate without whitespace, causing `line.split()` to merge tokens. Shear components S12/S13/S23 could be silently dropped, underestimating von Mises stress. Switched to column-offset parsing (matching `_parse_frd_displacement`), with split-based fallback.
- **Eval preview container zombie on timeout** (forge-api PR #45, `app/routes/eval_preview.py`): `proc.kill()` sends SIGKILL to the docker client subprocess, but the container continues running. Added named container + explicit `docker kill <name>` on `asyncio.TimeoutError`.
- **Preview container missing security flags** (forge-api PR #45): `--cap-drop ALL` and `--pids-limit 256` were present in CI eval sandbox but absent from the live preview endpoint.

## 2026-06-03 (session 8)

### Added
- **`min_wall_thickness_mm` geometric enforcement** (PR #229, `benchmark/geometry.py`): ray-cast cross-section sampler along X, Y, Z axes (8×8 grid per axis) rejects any solid chord shorter than the spec's minimum wall thickness minus 0.1mm print tolerance. X-rays exclude bolt-hole center positions to avoid flagging intentional clearance voids. Closes the known gap documented in the threat model.

### Documentation
- **Threat model updated** (PR #229, `docs/threat-model.md`): wall thickness check marked Implemented; removed Known Gap note.

## 2026-06-03 (session 7)

### Fixed
- **FEA convergence trigger lowered from 70% → 40%** (PR #226, `benchmark/fea.py`): the 4mm coarse mesh can underestimate stress in thin cross-sections by 30–50%. A miner could submit a thin-wall design sitting at ~65% of allowable on the coarse mesh and skip the fine-mesh check entirely. Lowering the threshold to 40% ensures these designs get the convergence gate.
- **Sandbox tests used old single-param signature** (PR #227, `tests/test_evaluate.py`): four sandbox tests were still using `generate(spec)` instead of `generate(spec, llm)`. The timeout test was failing outright; the other three passed only because the rejection message accidentally satisfied their error-string assertions.

### Documentation
- **Threat model accuracy** (PR #226, `docs/threat-model.md`): corrected convergence trigger from 70% → 40%; removed false claim about a geometric wall-thickness sampler (not implemented); added known-gap note for `min_wall_thickness_mm`.

## 2026-06-03 (session 2)

### Fixed
- **Baseline agent build-volume overflow** (PR #214, `agents/baseline/agent.py`): naive L-bracket used `max_bolt_coord + 20mm` for plate dimensions, exceeding build volume on some specs; also `shelf_thickness=12mm` fixed regardless of spec load-point Z, causing "too few nodes near load point" FEA failure. Fixed: all dimensions clamped to build volume with 2mm margin; shelf height computed from `load_point_mm[2]`.
- **CONTRIBUTING model IDs** (PR #215): model IDs were shown without provider prefix (`claude-haiku-4-5` vs `anthropic/claude-haiku-4-5`); corrected to match `FORGE_MODEL_WHITELIST` format. Added `llm-agent/` to examples list.

### Changed
- **score.yml serialization** (PR #216, `.github/workflows/score.yml`): add `concurrency: group: score-main, cancel-in-progress: false` to serialize post-merge full scoring runs. Prevents concurrent SQLite writes overwhelming forge-api at high miner volume.

## 2026-06-03

### Added
- **`forge specs` live SOTA state** (PR #204, `cli.py`): fetches `/sota` in one call and adds a SOTA column to the spec table — unclaimed specs shown as `OPEN` in green, claimed specs show the current score and contributor. `--unclaimed` flag filters to only show specs with no current leader.
- **Deterministic example agent** (PR #199, `examples/deterministic-agent/`): no-LLM agent using pure geometric rules — minimal arm for `mass_grams`, tall cross-section (h³ stiffness principle) for `stiffness_to_weight`, full build-volume fill for `deflection_mm`. README updated with examples table showing all three agent paradigms.
- **`forge status --round <id>`** (PR #195, `cli.py`): scope SOTA comparison to one round's 15 specs instead of all 54.
- **Docker build caching** (PR #195, `eval.yml`, `score.yml`): GitHub Actions GHA layer cache via `docker/build-push-action@v5`. Second and subsequent builds skip unchanged layers — significantly faster CI for miner PRs.
- **Thingiverse catalog specs** (PRs #206–#208, `specs/catalog/`): 30 catalog specs (10 each for mass_grams, stiffness_to_weight, deflection_mm). Inactive until added to a round JSON.

### Changed
- **Threat model accuracy** (PR #201, `docs/threat-model.md`): Threats 2/3/4/7 marked Implemented — plagiarism check, rate limiting, mesh convergence, and hidden eval set were all shipped but still listed as Planned.

### Fixed
- **`httpx.utils.quote` → `urllib.parse.quote`** (PR #205, `catalog/`): `httpx.utils` was removed in modern httpx; all ingest workflow runs were crashing on this.
- **Ingest workflow PR creation** (PR #209, `.github/workflows/ingest.yml`): replaced `peter-evans/create-pull-request@v7` (blocked by repo policy) with plain `git push` + compare URL.
- **Null-score crash in PR eval comment** (PR #200, `scripts/`): `evaluate.py` returns `score: null` on FEA failure; PR comment script was calling `.toFixed(2)` on null → TypeError → full comment step crashed. Failed rows now show `—` with failure reason; composite shows `—` when any category fails.
- **QUICKSTART reference implementations** (PR #200, `QUICKSTART.md`): `examples/deterministic-agent/` was missing from the reference list.
- **Stale `python cli.py` references in CLI output** (PR #196, `cli.py`): `forge new`, `forge rounds`, and help text printed `python cli.py ...` instead of `forge ...`.
- **`forge submit` leaderboard URL** (PR #197, `cli.py`): was linking to raw API JSON endpoint; now links to the dashboard UI (port 8080). Added `FORGE_DASHBOARD_URL` env var for overriding.
- **`forge submit` NameError** (PR #195, `cli.py`): `branch` was read before assignment if run outside a git repo.
- **QUICKSTART `--spec` example** (PR #195, `QUICKSTART.md`): showed a file path instead of a spec ID for `--spec`.
- **API version string** (forge-api PR #36, `main.py`): was `0.1.0` since initial scaffold; updated to `0.13.1`.

## 2026-06-02

### Added
- **Round 003 — Deflection minimization**: 15 specs (seeds 700/800/900, easy/medium/hard). Objective: minimize `deflection_mm`. High-modulus materials (Al, SS) are decisive.
- `deflection_mm` metric: `evaluate.py`, `generator.py`, CLI `--metric deflection_mm`, `METRIC_CONFIG` in API/dashboard.
- Eval PR comment now shows correct label, unit, and 4-decimal delta for `deflection_mm`; suppresses redundant FEA displacement row.
- **Round 002 — Stiffness-to-weight**: 15 specs (seeds 400/500/600). Objective: maximize `stiffness_to_weight`.
- **Private held-out eval set** (`scripts/generate_hidden_specs.py`, `scripts/run_hidden_eval.py`): 15 hidden specs (5 per round, seeds 9000–9204). Post-merge `score.yml` runs one hidden spec per round via forge-api admin endpoints. Threat 7 (eval overfitting) mitigated.
- **Spec rotation script** (`scripts/rotate_round.py`): closes a round, generates 15 fresh specs across easy/medium/hard tiers, posts Discord embed if `DISCORD_WEBHOOK_URL` is set. `--dry-run` for safe preview.
- **Seeded load-case perturbation** (`benchmark/fea.py: _perturb_load`): ±10% magnitude, ±5° direction deviation, seeded by `spec["id"]`. Miners see only nominal `load_newtons`; actual FEA load is opaque. Threat 8 (load-case overfitting) documented.
- **Source similarity check** (`benchmark/agent_similarity.py`, `scripts/check_source_similarity.py`): CI rejects agents with token similarity ≥ 0.95 vs any reference agent. Catches verbatim copies and rename-only clones.
- **Post-merge full-round eval** (`.github/workflows/score.yml`): after a miner PR merges, fans out to 3 parallel matrix jobs scoring all 15 specs per round; records to forge-api.
- **Pre-commit hooks** (`.pre-commit-config.yaml`): black + ruff + mypy for `benchmark/`, `scripts/`, `specs/`, `catalog/`. Install: `pip install pre-commit && pre-commit install`.
- **Metric-aware example** (`examples/metric-aware-agent/`): reads `spec["scoring"]["metric"]` and sends a tailored geometry strategy to the LLM per category.
- **`forge leaderboard --history <spec_id>`**: prints chronological SOTA progression for a spec. Fetches from `/sota/{spec_id}/history`.
- **Multi-spec pool eval in CI** (`scripts/select_eval_specs.py`, `run_eval_pool.py`, `record_submissions.py`): each PR is evaluated on one randomly-sampled easy spec from each of the 3 active rounds. PR comment shows cross-category table + composite score.
- **Per-spec SOTA reference STEPs** (`sota/{spec_id}/reference.step`): geometric similarity check is now per-spec first, falling back to the global reference.
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

### Changed
- **Dockerfile base pinned by digest** (`ubuntu:24.04@sha256:023f...`): prevents silent base-image changes from breaking eval parity across CI runs.

### Fixed
- **CLI metric units in eval output**: `forge eval` verbose output and summary table now use `_fmt_score(score, metric)` — round_002 shows `N/(mm·g)`, round_003 shows `mm`.
- **Template agent field names**: docstring corrected — `load_n` → `load_newtons`, `spec["safety_factor"]` → `spec["constraints"]["safety_factor"]`.
- **Unclaimed spec SOTA label**: CI now correctly applies the `optimization` label (2× Gittensor multiplier) when the first miner claims an unclaimed spec.
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
