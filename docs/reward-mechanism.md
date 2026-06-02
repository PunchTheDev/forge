# Reward Mechanism

A detailed analysis of how Forge allocates Bittensor emissions and why the design choices create genuine, durable competitive incentives.

---

## Overview

Forge is a Gittensor subnet 74 optimization repository. Miners earn a share of the network's contributor emissions by holding the SOTA (state-of-the-art) position — the lowest mass design that passes automated FEA. The emission allocation is designed to:

1. **Maximize incentive to beat the benchmark** — the top score earns the most, full stop.
2. **Reward continuous improvement** — an old SOTA decays. Staying on top requires real innovation.
3. **Resist gaming** — FEA is objective physics. You can't bribe CalculiX.
4. **Never saturate** — when scores converge, the frontier resets with a new spec.

---

## Emission allocation

```
Total subnet emissions = network_rate × time
                       = maintainer_cut (30%) + contributor_pool (70%)
```

The **maintainer** (PunchTheDev) earns 30% for running CI, reviewing PRs, evolving specs, and maintaining the benchmark harness. This is labor, not a free pass.

The **contributor pool** (70%) goes to miners based on a time-weighted score function.

---

## Contributor scoring function

A miner's emission share at time `t` depends on:

1. **Marginal gain** — how much did this design beat the previous SOTA?
2. **Time held** — how long has this design remained the top score?
3. **Decay** — old scores yield gradually to the new frontier.

### Step 1 — Marginal gain score

```
marginal_gain(s) = (baseline_mass − s.mass_grams) / baseline_mass
```

Where `baseline_mass` is the spec's reference design (180g for spec 001).

| Agent | Mass | Marginal Gain |
|-------|------|---------------|
| baseline | 180.0g | 0.0% |
| slim-spine | 108.5g | 39.7% |
| trim-frame | 56.8g | 68.4% |
| taper-beam | 38.7g | 78.5% |
| taper-slim | 34.1g | 81.1% |
| lean-arm | 32.6g | 81.9% |
| pocket-plate | 30.1g | 83.3% |
| deep-pocket | 29.2g | 83.8% |
| compact-arm | 27.2g | 84.9% |

Note that the first 100g of improvement earns proportionally more than the last 1g of convergence. This naturally front-loads reward for large gains while still paying for marginal refinements.

### Step 2 — Time decay (sigmoid)

The PR lookback window is **45 days**. Within that window, a design's reward weight decays according to:

```
decay(age_days) = 1 − σ((age_days − midpoint) / scale)
         where σ(x) = 1 / (1 + exp(−x))
               midpoint = 14 days
               scale = 5 days
```

| Age | Decay factor | Interpretation |
|-----|-------------|----------------|
| 0 days (new SOTA) | ~0.97 | Nearly full reward |
| 7 days | ~0.88 | Strong but decaying |
| 14 days | 0.50 | Half weight |
| 21 days | ~0.12 | Earning little |
| 30 days | ~0.02 | Nearly zero |
| 45 days | 0.00 | Outside window |

The sigmoid shape is intentional: it creates a **competitive urgency window** (days 7–21) where the current SOTA holder earns rapidly diminishing returns while a new challenger can earn maximum gain by posting a new leader.

### Step 3 — Emission share

Within each 24-hour epoch, the contributor pool is split across all miners who have ever held the SOTA, weighted by:

```
emission_share(m) = (marginal_gain(m) × decay(age(m))) / Σ(marginal_gain × decay for all active miners)
```

A miner with a **large gain AND a fresh design** earns the lion's share. A miner with a small gain or an aging design earns proportionally less.

---

## Why this structure creates strong incentives

### The arms race property

Under this structure, a new challenger can earn more in 2 weeks than the current SOTA holder earns in the next month. This creates an **arms race dynamic**: every miner's dominant strategy is to post a better design before the current holder's decay window closes.

### The innovation premium

A design that improves mass by 5g earns roughly 5× more marginal gain than a design that improves by 1g. Large innovations are disproportionately rewarded. This is correct — it's harder to find 5g of savings than 1g, and the competition benefits more from large steps.

### The floor resistance

As scores converge toward the physical floor (minimum structural mass), marginal gains shrink. Eventually, no single miner can earn meaningful emissions. This is the signal to add a new spec and reset the frontier.

When a new spec is added, it starts with the full baseline and the first miner to post a passing submission earns maximum marginal gain — recreating the early-days incentive spike.

---

## Anti-saturation mechanism

When top-5 scores converge to within **1% of each other**, the maintainer adds a new spec:

1. New problem definition added to `specs/`
2. New spec seeded in forge-api with a baseline submission
3. Competition opens — first mover earns maximum marginal gain
4. Old spec remains active, contributing to emissions for its 45-day lookback window

The spec backlog ensures there's always an open frontier. Forge is designed to have 5–10 active specs simultaneously, each at a different convergence stage.

---

## Multi-spec emission splitting

When multiple specs are active simultaneously, the contributor pool is split proportionally by spec activity:

```
spec_weight(s) = (total_submissions_last_30_days(s) + 1) / Σ(all active spec weights)
```

Active, competitive specs get more emissions. Saturated specs with no recent submissions get near-zero emissions. This creates a natural selection pressure: miners focus on specs with the most competitive room.

---

## What validators verify

Validators on SN74 verify:

1. **CI passed** — the GitHub Actions check passed for the PR
2. **Score authenticity** — the forge-api score matches CI output (tamper-evident via commit hash)
3. **Unique contribution** — geometric similarity check passed (not a copy of SOTA)
4. **Determinism** — 3× determinism check passed

Validators do **not** re-run FEA — they trust the CI container's fixed-dependency build. This is the appropriate trust model: the harness is open-source and forkable, so any miner can audit the eval stack.

---

## Gamability analysis

### Can a miner exploit the scoring function?

The score is `mass_grams` — a physical measurement from CAD geometry. To get a lower score without a lighter part, a miner would need to:

1. **Generate a hollow mesh** — geometry.py checks wall thickness (≥1.2mm) using ray-casting with OCP
2. **Exploit FEA mesh sensitivity** — mesh convergence check catches designs that pass only at coarse resolution
3. **Submit a near-copy** — geometric similarity check (≥95% → rejected) catches SOTA copies
4. **Use non-deterministic generation** — 3× determinism check catches stochastic agents

The compound probability of defeating all four independent checks is negligible. And since FEA is grounded in physics (mass × stress), there's no "adversarial example" against the laws of elasticity.

### Can the maintainer be gamed?

The maintainer reviews PRs before merge. A passing CI result is necessary but not sufficient — the maintainer can reject:
- Suspicious geometry that passes numerically but looks physically wrong
- Designs that exploit implementation bugs rather than structural optimization
- Agents that generate precomputed answers for the specific spec (this is technically legal but flagged as "non-generalizing" for future specs)

### Why is FEA-based scoring genuinely hard to game?

Other benchmarks suffer from Goodhart's Law: when a measure becomes a target, it ceases to be a good measure. FEA-based mass scoring resists this because:

1. **The check is simulation of real physics** — not a proxy or learned metric
2. **The safety factor (2.0×) adds headroom** against mesh artifacts
3. **Multiple failure modes** — geometry + FEA + convergence + similarity must all be defeated simultaneously

The only way to get a lower mass score is to actually design a lighter structural part. That IS the goal.

---

## Economic sustainability

Forge is registered on Gittensor SN74 (Gittensor's optimization subnet). Subnet validators allocate emissions to registered repos based on the quality and activity of contributions. Forge's competitive structure ensures:

- **Sustained activity** — miners have ongoing incentive to post new designs
- **Verifiable quality** — every submission is scored by deterministic CI
- **Expanding frontier** — new specs prevent saturation

For a validator assessing Forge: the benchmark measures a real economic capability (structural CAD optimization). The outputs are immediately useful engineering artifacts. This is not a toy benchmark — it's measuring something that matters in the real world.

---

## Further reading

- [scoring.md](scoring.md) — detailed FEA pipeline and geometry constraints
- [anti-gaming.md](anti-gaming.md) — threat model with specific attack/mitigation analysis
- [hyperparameters.md](hyperparameters.md) — raw Gittensor config values
