# Threat Model

This document describes the attack surface of the Forge benchmark and the mitigations in place or planned. It is meant to be read alongside `docs/scoring.md` and the CI workflow.

---

## Adversary goals

| Goal | Description |
|---|---|
| **Free-rider** | Earn the `optimization` label (2× Gittensor multiplier) without genuinely advancing SOTA |
| **Plagiarist** | Copy the current leader's agent verbatim or with cosmetic edits |
| **Spammer** | Flood the queue with low-effort submissions to saturate CI or accumulate label counts |
| **Exploiter** | Find a scoring shortcut that produces a low mass/high stiffness without real structural merit |
| **Code injector** | Execute arbitrary code on the CI runner via a malicious `agent.py` |

---

## Threat 1 — Marginal improvement gaming

**Attack:** Submit an agent that beats SOTA by a tiny amount (0.001 g), collect the label, repeat.

**Mitigations:**
- Marginal-gain rule (forge-api `GET /sota/{spec_id}/eligibility`):
  - 0–7 days: 1.0% improvement required
  - 7–30 days: 0.5% required
  - 30–90 days: 0.1% required
  - 90+ days: any improvement wins
- CI checks eligibility before applying the `optimization` label.
- Fallback (if API unreachable): raw score comparison — degrades to no margin check. Fix: always keep server reachable from Actions.

**Residual risk:** Low. The time-decay makes it harder to farm marginal gains indefinitely.

---

## Threat 2 — Plagiarism / code cloning

**Attack:** Clone the current SOTA agent source or STEP file verbatim (or with trivial variable renames).

**Mitigations:**
- STEP geometric similarity check against `sota/reference.step` using `benchmark/similarity.py`.
- Submissions with similarity ≥ 0.95 are rejected (`stage: similarity`).
- Agent source-code diff can be manually inspected by maintainer before merge.

**Residual risk:** Low. Both STEP geometry and agent source are checked for similarity against all prior submissions.

**Implemented (PR #175):** `benchmark/agent_similarity.py` tokenizes agent source and computes similarity against every previously accepted agent. CI rejects submissions with similarity ≥ 0.95 — catches verbatim copies and rename-only clones. `scripts/check_source_similarity.py` runs as a CI step before eval.

---

## Threat 3 — Submission spam

**Attack:** Submit dozens of randomized agents, hoping one beats SOTA by luck or hash-based dedup.

**Mitigations:**
- Commit-hash dedup: CI checks `FORGE_API_URL/submissions?commit_hash=...`. If the commit was already evaluated, the eval is skipped. Cost-per-spam attempt is therefore the cost of a fresh commit, not CI minutes.
- Gittensor hyperparameter `excessive_pr_penalty_base_threshold: 3` — miners who open >3 PRs in a lookback window take a credibility penalty.
- `max_open_pr_threshold: 10` — PRs beyond 10 open at once are ignored by the validator.

**Residual risk:** Low-medium. Per-miner rate limit is in place; determined actors can still spray unique commits within the daily window.

**Implemented:** Per-contributor daily eval budget via `MAX_EVALS_PER_DAY` env var in forge-api (default configurable). Exceeding the limit returns HTTP 429. The Gittensor `excessive_pr_penalty_base_threshold: 3` adds a credibility penalty on top.

---

## Threat 4 — Geometry exploitation

**Attack:** Produce a geometry that tricks the scoring pipeline into reporting an artificially low mass or high stiffness-to-weight — e.g., a near-zero-thickness shell that passes geometry gates but deflects instantly under load.

**Mitigations:**
- FEA gate: CalculiX linear statics must pass; max stress ≤ allowable stress.
- Build volume, bolt pattern, overhang angle, and minimum wall thickness checked by `benchmark/geometry.py`.
- 2× determinism check on the first spec: CI runs spec 0 twice; if the score differs, the submission is flagged non-deterministic and rejected. Remaining specs run once to keep CI time manageable. (Note: stochastic agents that vary only on later specs could slip through — improving this is a known gap.)

**Implemented:** Two-density FEA mesh convergence. Eval runs a coarse mesh (4mm), and if max stress exceeds 40% of allowable, re-runs at fine density (2.5mm). Submissions with >10% stress deviation between densities are flagged as mesh-dependent and rejected. The 40% threshold (down from 70%) is deliberate: a 4mm coarse mesh can underestimate stress in thin cross-sections by 30–50%, so designs at 50–65% coarse stress still get the fine-mesh check.

**Implemented:** `min_wall_thickness_mm` enforced by a ray-cast cross-section sampler in `geometry.py`. Rays along X, Y, and Z axes sample an 8×8 grid of transverse positions; any solid chord shorter than the spec's minimum (minus 0.1mm print tolerance) is rejected. X-rays exclude bolt-hole centers to avoid flagging intentional clearance voids. The FEA convergence gate at 40% remains as a complementary mitigation for borderline designs.

---

## Threat 5 — Code injection (malicious `agent.py`)

**Attack:** An `agent.py` that:
- Reads host files via the mounted `/forge` volume
- Exfiltrates data via HTTP (agent has network access for LLM calls)
- Forks indefinitely (fork bomb) to exhaust CI resources
- Escapes the container via capability exploitation

**Mitigations currently in place:**
- Docker container with `--security-opt no-new-privileges` — prevents privilege escalation via setuid binaries.
- `--cap-drop ALL` — no Linux capabilities. Eliminates: raw socket creation, mounting filesystems, ptrace, kernel module loading, etc.
- `--memory 4g` — OOM kill before RAM exhaustion.
- `--cpus 2` — CPU throttling.
- `--pids-limit 256` — limits process tree size; fork bomb exhausts PID quota before impacting host.
- `TIMEOUT_SECONDS = 180` in `benchmark/sandbox.py` — wall-clock kill.
- Volume mount is read-write for `/forge` (needed for STEP output) — see residual risk below.

**Residual risk:**
- Network access is intentionally enabled (agent needs it for LLM API calls). A malicious agent could exfiltrate data from the `/forge` volume or make arbitrary outbound HTTP calls. The key `FORGE_LLM_KEY` is injected as an env var — a malicious agent could leak it.
- The mounted volume is writable. An agent could corrupt spec files or other workspace files (mitigated by: CI runs on fresh checkout; corrupted files don't persist to the repo).
- Container escape via kernel CVEs is theoretically possible; kept low by running on GitHub-hosted runners (ephemeral, short-lived, updated regularly).

**Planned:** Network egress proxy that allowlists only `openrouter.ai`. This eliminates data exfiltration and key leakage while preserving LLM access. Short-term workaround: rotate `FORGE_LLM_KEY` regularly; use a key scoped to the minimum required spend.

---

## Threat 6 — Sybil submissions

**Attack:** Create multiple GitHub accounts to circumvent per-miner rate limits or credibility thresholds.

**Mitigations:**
- Gittensor credibility score (`min_credibility: 0.70`) — new accounts with no contribution history start below threshold.
- `min_valid_merged_prs: 1` — first PR must be reviewed and merged by maintainer before earning rewards.

**Residual risk:** Low in the short term (high friction to create credible accounts). Increases if the repo becomes high-value enough to make account farming worthwhile.

---

## Threat 7 — Eval overfitting (held-out set leakage)

**Attack:** Optimize an agent specifically to the public spec set. Future rounds rotate, but a miner who memorizes all published specs can cache solutions.

**Mitigations:**
- Public spec IDs are known but procedurally generated — parameters vary per spec, not per "problem template". An agent that memorizes spec IDs would need to hard-code each solution individually.
- Round rotation: each round introduces new specs. Old SOTA carries over but new specs have no historical submissions.

**Residual risk:** Medium. A determined miner could build per-spec lookup tables. 

**Mitigated:** Private held-out spec set implemented (PR #181). 15 hidden specs (5 per round, seeds 9000–9204) are stored in the forge-api database only — never committed to this repo. After a PR merges, `score.yml` fetches one random hidden spec per round via `GET /admin/hidden/specs/{round}/sample` (requires `FORGE_ADMIN_KEY`) and evaluates the merged agent against it. Results are stored in `hidden_submissions` for maintainer review. Operators seed hidden specs by running `scripts/generate_hidden_specs.py` and setting `HIDDEN_SPECS_JSON` on the forge-api server. Hash-commitment (miner submits hash before spec is revealed) remains a longer-term hardening option.

---

## Threat 8 — Load-case overfitting

**Attack:** Tune a design exactly to the published nominal load (magnitude and direction). For example, a miner could orient internal ribs precisely along the known force direction, producing a design that excels at exactly 500 N downward but would fail or underperform at 490 N or 5° off-axis.

**Mitigations:**
- **Implemented: Load-case perturbation** (`benchmark/fea.py: _perturb_load`). The actual load applied in FEA is seeded by `spec_id` (not published in spec JSON). Perturbation: ±10% magnitude, ±5° polar deviation from nominal -Z direction. Miners see only `load_newtons` in the spec file; the actual load is deterministic per spec but opaque without reading the source.
- All submissions for the same spec face the same perturbed load — leaderboard scores remain comparable.
- `applied_load_n` is returned in eval JSON for transparency.

**Residual risk:** Low-medium. A miner who reads `fea.py` can compute the exact perturbation from `spec_id`. The cost of doing so is non-trivial and provides at most ±10%/±5° intelligence — not a meaningful exploit for well-engineered designs.

---

## Threat 9 — Specialist gaming (leaderboard breadth gap)

**Attack:** Enter only 3 easy specs (one per round) and achieve #1 on all three. Under an avg_rank model, this yields avg_rank = 1.0 — ranking above a well-rounded agent that competes on all 45 specs but averages rank 1.5.

**Mitigations:**
- **Implemented:** Overall leaderboard now sorts by `overall_score` — mean normalized performance across ALL active specs. Unentered specs count as 1.0 (baseline) in the mean. A miner who skips 42 specs cannot achieve overall_score < 1.0, so they rank below any agent that beats baseline across the full problem pool.
- This directly rewards breadth: entering more specs and beating baseline on each one lowers your overall_score.

**Residual risk:** Low. A miner who is genuinely #1 on every spec they enter still benefits from entering more specs — better coverage further reduces their overall_score.

---

## Threat 10 — Predictable spec selection

**Attack:** CI previously selected one easy spec per round using `PR_NUMBER % len(easy_specs)`. PR numbers are sequential and publicly visible. A miner can predict exactly which spec they'll face before opening the PR (by counting existing PRs), then optimize their agent specifically for that spec to maximize the chance of beating SOTA and earning the `optimization` Gittensor label (2× reward multiplier).

**Mitigations:**
- **Implemented (PR #222):** Spec selection now uses SHA-256(`GITHUB_RUN_ID:COMMIT_SHA`) as the index seed. `GITHUB_RUN_ID` is assigned by GitHub Actions at workflow trigger time — after the PR is opened — making it impossible to predict at commit time. Falls back to PR number only for local testing.

**Residual risk:** Very low. A determined miner could mine commits (like PoW) to influence `COMMIT_SHA`, but the additional `GITHUB_RUN_ID` entropy negates this.

---

## Threat 11 — CI queue saturation at scale

**Attack:** With 100+ miners each submitting multiple PRs per day, the eval queue could back up severely. Each eval takes ~15–45 minutes (3 Docker containers, FEA + mesh convergence). 100 concurrent PRs × 45 min = 75 hours queue depth for late arrivals.

**Mitigations:**
- `concurrency: cancel-in-progress: true` in eval.yml — only one eval runs at a time per PR branch.
- Commit-hash dedup — same commit never re-evaluated.
- GitHub Actions queuing naturally throttles burst load.
- Gittensor `max_open_pr_threshold: 10` and `excessive_pr_penalty_base_threshold: 3` discourage PR spam at the reward layer.

**Residual risk:** Medium at 100+ miners. CI eval capacity is bounded by GitHub Actions concurrent runner availability. Migration to on-demand ephemeral compute (Daytona or self-hosted) is the long-term fix. For launch, GitHub-hosted runners are sufficient at <50 concurrent miners.

---

## Summary table

| Threat | Severity | Status |
|---|---|---|
| Marginal improvement gaming | High | Mitigated (marginal-gain rule) |
| Plagiarism / code cloning | Medium | Mitigated (STEP + source similarity checks) |
| Submission spam | Medium | Partially mitigated (commit dedup, rate limit, Gittensor penalties) |
| Geometry exploitation | Medium | Mitigated (FEA + geometry gates + two-density mesh convergence) |
| Code injection | High | Partially mitigated (`--cap-drop ALL`, `--pids-limit`) |
| Sybil submissions | Low | Mitigated (credibility + min PR requirement) |
| Eval overfitting | Medium | Mitigated (hidden spec set + rotation) |
| Load-case overfitting | Low | Mitigated (seeded load perturbation in FEA) |
| Specialist gaming | Medium | Mitigated (breadth-normalized overall_score) |
| Determinism check coverage | Low | Partial — only spec 0 runs 2× (gap: stochastic agents may vary on later specs) |
| Predictable spec selection | Medium | Mitigated (run_id entropy — PR #222) |
| CI queue saturation | Medium | Partial — bounded by GitHub Actions capacity; Daytona migration needed at 100+ miners |
