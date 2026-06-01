# Gittensor Hyperparameter Configuration

Mapping of Gittensor subnet 74 hyperparameters to Forge's competition design.

## Configured values

| Parameter | Value | Rationale |
|---|---|---|
| `maintainer_cut` | 30% | Maintainer reviews PRs, runs CI, updates SOTA, evolves specs. High effort warrants meaningful cut. |
| `contributor_cut` | 70% | Goes to miners who beat the SOTA. Winner-takes-most drives competition. |
| `issue_discovery_share` | 0% | No issue rewards. This is a pure optimization competition — issues are irrelevant. |
| `pr_lookback_days` | 45 | Miners holding SOTA earn emissions for up to 45 days before a new leader displaces them. |
| `time_decay_midpoint_days` | 14 | Reward for old SOTA holders decays sigmoidally; half-value at 14 days. Incentivizes staying competitive. |
| `min_stake_to_submit` | default | No custom gating — open to all miners. |

## Labels and reward multipliers

| Label | Multiplier | Use case |
|---|---|---|
| `optimization` | 2.0× | PRs that set a new SOTA mass score |
| `maintenance` | 0.75× | Benchmark harness fixes, spec additions, CI improvements |
| `refactor` | 0.1× | Code cleanup with no functional change — minimal reward |

## Why winner-takes-most

Forge is a leaderboard competition. The miner holding SOTA should earn the majority of contributor emissions — this maximizes incentive to actually beat the benchmark rather than submit noise.

Decay over 45 days means a stale SOTA gradually yields more emissions to the next challenger, preventing a single submission from earning forever on a cold benchmark.

## Anti-saturation mechanism

When scores converge within ~1% across the top 5 submissions, the maintainer adds a new spec with tighter constraints. This resets the competitive frontier and restarts the emission race.

New specs get the `optimization` label automatically for the first 30 days.
