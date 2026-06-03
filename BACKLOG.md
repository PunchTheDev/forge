# Forge Backlog

Ordered by priority. Completed items are not tracked here — see `CHANGELOG.md`.

---

## Blocked on operator

- [ ] **Gittensor registration** — submit `docs/gittensor-registration.md` config to entrius/gittensor team
- [ ] **Discord SOTA alerts** — set `DISCORD_WEBHOOK_URL` on ventura-nanoclaw, then `pm2 restart forge-api`
- [ ] **Thingiverse ingestion** — provide Thingiverse API key; `forge ingest` pipeline is built and ready

---

## Anti-gaming hardening

- [ ] **AST/source similarity check** — compare submitted `agent.py` against all prior merged agents; reject if token similarity > threshold. STEP geometric similarity is live; source-code clones are a residual risk.
- [ ] **Private held-out eval set** — specs not in the repo, evaluated server-side only. Prevents overfitting to visible test specs. Requires server-side eval infra beyond Docker-in-CI.
- [ ] **Spec rotation schedule** — monthly rotation of active round specs, announced via Discord. Prevents long-term overfitting to fixed spec set.

---

## Future rounds

- [ ] **Round 004 spec set** — run `python -m specs.generator --n 15 --round 4 --seed 1000` to generate; activate via `rounds/round_004.json`. Waiting until rounds 1–3 are competitive.
- [ ] **Round 005 spec set** — harder tier or new geometry family (T-bracket, pipe mount). Define new Tier entry in `specs/generator.py` first.

---

## Hardening (low priority)

- [ ] Pin Docker image by digest (not tag) in CI — prevents silent image changes breaking eval parity
- [ ] Randomized load-case perturbations (±10% load, ±5° direction) — hardens against stress-test gaming
- [ ] Pre-commit hooks (black, ruff, mypy) for `benchmark/` code — local dev quality gate
