# Threat Model & Anti-Gaming

## Design principle

The benchmark must be resistant to gaming without becoming opaque. Every mitigation is documented here so its effectiveness can be audited.

---

## Threat 1: Copying the SOTA geometry

**Attack:** Miner downloads the current SOTA STEP file and submits it as their own.

**Mitigation:**
- Geometric similarity check (Hausdorff distance / volume overlap) against current SOTA runs at eval time. Submissions ≥95% similar are flagged.
- Reward function is `marginal_gain = sota_score - submission_score`. A copy scores 0 gain → 0 emissions reward.
- First-to-commit wins: a copy submitted after the original earns nothing even if the diff passes.

**Residual risk:** A miner could copy with trivial differences (scale, translate). Hausdorff check mitigates most cases.

---

## Threat 2: Exploiting the scoring function (Goodhart's Law)

**Attack:** Find a geometry that minimizes mass by exploiting implementation bugs in FEA/geometry checks rather than genuine structural performance.

**Mitigation:**
- FEA uses CalculiX linear statics with a deterministic mesh — an industry-standard solver with no known mass-minimizing exploits.
- Safety factor of 2.0 provides headroom against mesh-sensitivity artifacts.
- Suspicious results (stress far below allowable combined with very low mass) trigger a manual maintainer review before SOTA is updated.

**Residual risk:** Numerical edge cases in gmsh meshing could produce inconsistent stress results for pathological geometries (e.g., very thin shells). Determinism check (3× eval) catches most of these.

---

## Threat 3: Non-deterministic agents (random search at eval time)

**Attack:** Agent runs stochastic search during the 60s window, producing different STEP files each run.

**Mitigation:**
- 3× determinism check: all three eval runs must return the same score. Any deviation → rejection.
- If an agent uses randomness internally, it must fix seeds before the generate() call.

**Residual risk:** An agent could fix seeds only in the generate() path and produce consistent results while still using internal randomness that is irreproducible outside CI. Acceptable — the submitted artifact is what matters.

---

## Threat 4: Sybil submissions (many accounts, minor variants)

**Attack:** Create many GitHub accounts, submit minor variants to farm emissions.

**Mitigation:**
- Geometric similarity check across all historical submissions. Near-identical geometries from different contributors are flagged.
- Gittensor's native Sybil resistance (stake-weighted validator scoring).
- Rate limit: one scored eval per contributor per 24h.

**Residual risk:** Motivated Sybil attackers with distinct IP addresses and genuine geometric variation. Rate limits reduce reward-per-account to sub-economic levels.

---

## Threat 5: Overfitting to the public test spec

**Attack:** Construct a geometry that passes spec 001 exactly but would fail under any variation (e.g., slightly different load point).

**Mitigation:**
- FEA uses a volumetric mesh with 4mm elements — coarse enough to be robust against pixel-perfect tuning.
- Future specs will vary load points, bolt patterns, and materials. A solution that overfits spec 001 fails spec 002.
- The safety factor (2.0×) means the part must survive twice the stated load, providing generalization margin.

**Residual risk:** None significant for a structural benchmark — the laws of physics don't have edge cases.

---

## Threat 6: Wall-clock gaming (fast/slow agents)

**Attack:** Submit an agent that generates a precomputed answer instantly, circumventing the "spirit" of optimization.

**Mitigation:** Not a threat. The benchmark is about the artifact (STEP file), not the method. Precomputed answers are fine — the miner still had to compute them once, and the geometry must beat the current SOTA.

---

## Threat 7: CI resource exhaustion

**Attack:** Submit an agent that consumes excessive CPU/memory in the eval container, blocking other evaluations.

**Mitigation:**
- Hard resource limits in `benchmark/sandbox.py`: 60s CPU, 4 GB RAM.
- Docker container provides additional isolation.
- Daytona ephemeral sandboxes ensure no cross-contamination between evaluations.
