# Gittensor Registration

How to register Forge on Gittensor subnet 74 so miners earn real emissions.

---

## What registration means

Gittensor maintains a list of approved repositories in
`entrius/gittensor/gittensor/validator/weights/master_repositories.json`.
Adding Forge to this file is the only registration step. Validators pick it up
on their next sync cycle.

The Gittensor team controls who gets added. You submit a request via their
Discord or by opening a PR on `entrius/gittensor`. The team reviews, approves,
and merges. After that, miners on subnet 74 start earning emissions for merged
PRs on Forge.

---

## Our config entry

Submit this block for `PunchTheDev/forge`:

```json
"PunchTheDev/forge": {
  "emission_share": 0.02,
  "issue_discovery_share": 0.0,
  "maintainer_cut": 0.30,
  "trusted_label_pipeline": true,
  "default_label_multiplier": 0.0,
  "label_multipliers": {
    "optimization": 2.0,
    "passed": 0.0,
    "maintenance": 0.5,
    "refactor": 0.1
  },
  "eligibility": {
    "min_valid_merged_prs": 1,
    "min_credibility": 0.70,
    "excessive_pr_penalty_base_threshold": 3,
    "max_open_pr_threshold": 10,
    "open_issue_spam_base_threshold": 0,
    "max_open_issue_threshold": 0
  },
  "scoring": {
    "pr_lookback_days": 45,
    "review_penalty_rate": 0.30,
    "src_tok_saturation_scale": 30,
    "time_decay": {
      "grace_period_hours": 12,
      "sigmoid_midpoint_days": 14,
      "min_multiplier": 0.0
    }
  }
}
```

### Field rationale

| Field | Value | Why |
|---|---|---|
| `emission_share` | `0.02` | Starting share — ask the team what's appropriate at launch |
| `issue_discovery_share` | `0.0` | No issue-filing rewards. Forge is pure optimization. |
| `maintainer_cut` | `0.30` | 30% routes to the maintainer before contributor scoring |
| `trusted_label_pipeline` | `true` | CI applies the `optimization` label via GitHub Actions. Without this, app-actor labels are ignored. |
| `default_label_multiplier` | `0.0` | Unlabeled PRs earn nothing. Forces labels as the earning gate. |
| `label_multipliers.optimization` | `2.0` | Applied by CI when a PR sets a new SOTA. Double weight — this is the primary earn path. |
| `label_multipliers.passed` | `0.0` | CI applies to PRs that pass but don't beat SOTA. Explicitly zero — passing isn't earning. |
| `label_multipliers.maintenance` | `0.5` | Maintainer applies manually: benchmark fixes, spec additions, CI work. |
| `label_multipliers.refactor` | `0.1` | Code cleanup with no functional change — minimal reward. |
| `eligibility.min_valid_merged_prs` | `1` | One merged SOTA to qualify. Lower barrier than default (3). |
| `eligibility.min_credibility` | `0.70` | Slightly relaxed — miners will have closed (non-merged) PRs by design. |
| `eligibility.excessive_pr_penalty_base_threshold` | `3` | Up to 3 open PRs before spam penalty. Miners hold attempts across specs. |
| `eligibility.max_open_issue_threshold` | `0` | Hard cap: no open issues allowed. Issue discovery is disabled. |
| `scoring.pr_lookback_days` | `45` | Extended window — reward holders for 6 weeks before decay zeroes out. |
| `scoring.review_penalty_rate` | `0.30` | CI rejections cost 30% (vs 15% default). Accurate eval; don't spam. |
| `scoring.src_tok_saturation_scale` | `30` | Saturates fast — focused algorithmic PRs, not volume. |
| `scoring.time_decay.sigmoid_midpoint_days` | `14` | Half-weight at 14 days. Creates urgency to post a new leader within 2 weeks. |
| `scoring.time_decay.min_multiplier` | `0.0` | Old SOTAs go to zero. No free ride for stale designs. |

---

## How the label pipeline works

The eval CI (`eval.yml`) automatically applies labels based on result:

- **`optimization`** — PR beats the current SOTA score. This is the earning label.
  Validators see this + `trusted_label_pipeline: true` → 2.0× multiplier on the score.
- **`passed`** — PR passes all constraints but does not beat SOTA. Earns nothing
  (multiplier = 0.0), but confirms the design is structurally valid.

The CI has `issues: write` permission and creates the labels on first use if
they don't already exist. No manual setup needed.

---

## What the maintainer applies manually

The maintainer (`PunchTheDev`) applies these labels to non-agent PRs:

| Label | For | Multiplier |
|---|---|---|
| `maintenance` | Spec additions, benchmark fixes, CI improvements | 0.5× |
| `refactor` | Code cleanup, no functional change | 0.1× |

Without one of these labels, a non-agent PR earns nothing
(`default_label_multiplier: 0.0`).

---

## Steps to register

1. **Confirm all forge PRs are merged** — validators query the live repo. CI must
   be functional before registration.

2. **Confirm CI labels are wired** — open a test PR with a working agent to verify
   `optimization` or `passed` gets applied automatically.

3. **Contact the Gittensor team** via their Discord (or open a PR on
   `entrius/gittensor`). Provide:
   - Repository: `PunchTheDev/forge`
   - The JSON block above
   - A brief description: *"Competitive parametric CAD optimization. Miners submit
     Python agents that generate STEP files. Scored by FEA (CalculiX) — lowest
     mass that survives the load wins. CI applies optimization label on SOTA beat."*

4. **After approval** — the team adds Forge to `master_repositories.json` and
   merges. Emission allocation becomes active on the next validator cycle.

5. **Set `emission_share`** — the initial value (suggested `0.02`) may be adjusted
   by the team based on repo activity and approval policy. Confirm before they merge.

---

## After registration

- Miners start showing up. Monitor PR volume — the first SOTA-beat PRs should
  arrive within a few days if the repo is visible.
- If volume is low, check that the `FORGE_LLM_KEY` secret and `FORGE_API_URL` are
  set so the CI pipeline is fully functional.
- When spec scores converge, add new specs to keep the frontier open.
- Adjust `emission_share` over time via the Gittensor team as the repo demonstrates
  sustained activity and quality.
