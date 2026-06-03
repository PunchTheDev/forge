# Forge Backlog

Ordered by priority. Completed items are not tracked here — see `CHANGELOG.md`.

---

## Blocked on operator

- [ ] **Gittensor registration** — submit `docs/gittensor-registration.md` config to entrius/gittensor team
- [ ] **Discord SOTA alerts** — set `DISCORD_WEBHOOK_URL` on ventura-nanoclaw, then `pm2 restart forge-api`
- [ ] **Thingiverse ingestion** — provide Thingiverse API key; `forge ingest` pipeline is built and ready

---

## Anti-gaming hardening

- [ ] **Private held-out eval set** — specs not in the repo, evaluated server-side only. Prevents overfitting to visible test specs. Requires server-side eval infra beyond Docker-in-CI.
- ~~Spec rotation schedule~~ — shipped (PR #180, `scripts/rotate_round.py`; Discord embed on `DISCORD_WEBHOOK_URL`)

---

## Future rounds

- [ ] **Round 004 spec set** — run `python3 scripts/rotate_round.py --close round_001 --new round_004 --metric mass_grams --seeds-base 1000`. Waiting until rounds 1–3 are competitive.
- [ ] **Round 005 spec set** — harder tier or new geometry family (T-bracket, pipe mount). Define new Tier entry in `specs/generator.py` first.

---

## Hardening (low priority)

- ~~Randomized load-case perturbations~~ — shipped (PR #179, seeded by spec_id in `benchmark/fea.py`)
