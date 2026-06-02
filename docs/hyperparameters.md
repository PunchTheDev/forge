# Gittensor Hyperparameter Configuration

Mapping of every Gittensor subnet 74 hyperparameter to Forge's competition design.
Field names and defaults sourced directly from `gittensor/validator/utils/load_weights.py`
and `gittensor/constants.py`.

---

## Top-level repository fields

| Field | Our value | Default | Range | Rationale |
|---|---|---|---|---|
| `emission_share` | TBD (set by team) | — | [0, 1] | Fraction of subnet emission pool allocated to Forge. Grows as the repo earns adoption and quality signal. |
| `issue_discovery_share` | `0.0` | `0.5` | [0, 1] | No issue-filing rewards. Forge is a pure optimization competition; issue discovery creates noise without value. |
| `maintainer_cut` | `0.30` | `0.0` | [0, 1] | 30% of the repo's emission slice routes to the maintainer (Punch) before contributor scoring. Covers review, CI, SOTA updates, spec evolution. |
| `additional_acceptable_branches` | `null` | `null` | list | Only PRs merged to the default branch count. No side branches. |
| `trusted_label_pipeline` | `true` | `false` | bool | Forge CI applies scoring labels via GitHub Actions (a GitHub App actor). Without this flag, app-applied labels are ignored. |
| `label_multipliers` | see below | `null` | dict | Per-label reward multipliers. Keys support fnmatch wildcards. |
| `default_label_multiplier` | `0.0` | `1.0` | float | PRs with no recognized label get zero reward. Prevents unlabeled noise from earning. |
| `fixed_base_score` | `null` | `null` | [0, 100] | Not overriding the base score formula. Let token complexity drive it. |

### Label multipliers

| Label | Multiplier | Applied when |
|---|---|---|
| `optimization` | `2.0` | PR sets a new SOTA score (harness applies automatically) |
| `maintenance` | `0.5` | Benchmark fix, spec addition, CI improvement (maintainer applies) |
| `refactor` | `0.1` | Code cleanup with no functional change — minimal reward |

The `optimization` label is the primary earning path for miners. Everything else is explicitly discounted.

---

## Eligibility config (`eligibility.*`)

These control whether a miner is considered credible enough to receive any score at all from this repo.

| Field | Our value | Default | Rationale |
|---|---|---|---|
| `min_valid_merged_prs` | `1` | `3` | Lower barrier to entry: a miner only needs 1 merged SOTA PR to qualify. Forge is competitive, not volume-based. |
| `min_credibility` | `0.70` | `0.80` | Slightly relaxed credibility gate — miners iterating toward SOTA will have some closed (non-merged) PRs by design. |
| `excessive_pr_penalty_base_threshold` | `3` | `2` | Allow up to 3 open PRs before spam penalty kicks in. Miners may hold in-progress attempts across multiple specs simultaneously. |
| `open_pr_threshold_token_score` | `300.0` | `300.0` | Default. Each 300 token-score earned unlocks one extra open PR slot. |
| `max_open_pr_threshold` | `10` | `30` | Cap at 10 open PRs total. Forge has multiple active specs but not dozens. |
| `min_valid_solved_issues` | `1` | `3` | Issue discovery not used (`issue_discovery_share=0`), so this is irrelevant. Setting 1 to avoid validator errors if the field is required. |
| `min_issue_credibility` | `0.80` | `0.80` | Default — issue discovery disabled. |
| `min_token_score_for_valid_issue` | `5.0` | `5.0` | Default — issue discovery disabled. |
| `open_issue_spam_base_threshold` | `0` | `2` | No open issues expected; set to 0 to block any accidental issue spam. |
| `open_issue_spam_token_score_per_slot` | `300.0` | `300.0` | Default. |
| `max_open_issue_threshold` | `0` | `30` | Hard cap: no open issues allowed. |

---

## Scoring config (`scoring.*`)

These tune the scoring formula itself — how much a given merged PR earns.

| Field | Our value | Default | Range | Rationale |
|---|---|---|---|---|
| `pr_lookback_days` | `45` | `30` | [1, 90] | Extended window: miners holding SOTA earn emissions for up to 45 days before a new leader displaces them. Incentivizes genuine improvements over churn. |
| `open_pr_collateral_percent` | `0.20` | `0.20` | [0, 1] | Default. 20% of a PR's potential score is held as collateral while the PR is open, released on merge. Standard anti-spam. |
| `review_penalty_rate` | `0.30` | `0.15` | (0, 1] | 30% deduction per maintainer CHANGES_REQUESTED review (vs 15% default). Forge CI is automated and precise — if the harness requests changes, the PR has a real problem. Sharper penalty discourages gaming. |
| `standard_issue_multiplier` | `1.0` | `1.33` | [1, 5] | Issue discovery disabled; set to neutral so any edge-case issue PR doesn't earn a bonus. |
| `maintainer_issue_multiplier` | `1.0` | `1.66` | [1, 5] | Same rationale — issue discovery disabled. |
| `src_tok_saturation_scale` | `30.0` | `58.0` | [10, 500] | Faster saturation: a PR reaches ~63% of base score cap at 30 tokens of complexity rather than 58. Forge PRs are focused optimizations — the value is in correctness + novelty, not raw size. |

### Time decay (`scoring.time_decay.*`)

The time-decay curve controls how an old SOTA submission's score decays over the lookback window.

| Field | Our value | Default | Range | Rationale |
|---|---|---|---|---|
| `grace_period_hours` | `24` | `12` | [0, 168] | 24-hour grace: a new SOTA starts earning at full rate for its first day. |
| `sigmoid_midpoint_days` | `14` | `10` | [1, 90] | Score halves at 14 days (vs 10 default). Moderate pressure: a two-week-old SOTA still earns meaningfully, but a month-old one has decayed substantially. |
| `sigmoid_steepness` | `0.35` | `0.40` | [0.01, 5] | Slightly gentler sigmoid (0.35 vs 0.40). Smoother transition between earning and non-earning states. |
| `min_multiplier` | `0.05` | `0.05` | [0, 1] | Default. A stale SOTA retains 5% of score through the full lookback window — keeps it from going to zero and rewards long-term benchmark health. |

---

## Scoring model summary

A merged PR's earned score flows through this pipeline:

```
base_score    = 25 × (1 − exp(−src_tok / src_tok_saturation_scale))
              + min(total_score / 1500, 1) × 5          # cross-repo contribution bonus

              × issue_multiplier       (1.0x — issues disabled)
              × label_multiplier       (2.0x if optimization, else 0.0x for unlabeled)
              × review_quality         (1.0 − 0.30 × changes_requested_reviews)
              × time_decay             (sigmoid from 1.0 → 0.05 over 45d lookback)
              × credibility            (0 if below 0.70 credibility threshold)
              × spam_multiplier        (0 if > threshold open PRs, else 1)
```

70% of that earned score flows to miners (contributor pool).
30% flows to the maintainer before any contributor scoring.

---

## Anti-gaming design (hyperparameter angle)

- `default_label_multiplier: 0.0` — unlabeled PRs earn nothing. Miners cannot submit noise and earn by volume.
- `review_penalty_rate: 0.30` — automated CI rejections carry a real cost per round-trip.
- `min_valid_merged_prs: 1` + `min_credibility: 0.70` — low entry bar but credibility gate filters pure-spam accounts.
- `issue_discovery_share: 0.0` — removes the issue-filing attack surface entirely.
- `src_tok_saturation_scale: 30` — large PRs with no real improvement don't score significantly better than small precise ones.

See `docs/anti-gaming.md` for the full threat model.
