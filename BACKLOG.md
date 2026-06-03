# Forge Backlog

Ordered by priority. Completed items are not tracked here — see `CHANGELOG.md`.

---

## Blocked on operator

- [ ] **Gittensor registration** — submit `docs/gittensor-registration.md` config to entrius/gittensor team
- [ ] **Discord SOTA alerts** — set `DISCORD_WEBHOOK_URL` on ventura-nanoclaw, then `pm2 restart forge-api`
- ~~**Thingiverse ingestion**~~ — done (session 10, PRs #235–241). 65 catalog specs seeded (mass_grams, stiffness_to_weight, deflection_mm).
- [ ] **Hidden eval activation** — run `scripts/generate_hidden_specs.py` (payload generated, see STATE.md), set `HIDDEN_SPECS_JSON` + `FORGE_ADMIN_KEY` on ventura-nanoclaw, then `pm2 restart forge-api`.

---

## Anti-gaming hardening

- ~~**Private held-out eval set**~~ — shipped (PR #181). 15 hidden specs seeded via `HIDDEN_SPECS_JSON` env var in forge-api; post-merge `score.yml` evaluates one hidden spec per round. Operator must run `scripts/generate_hidden_specs.py` and set `HIDDEN_SPECS_JSON` + `FORGE_ADMIN_KEY` on server.
- ~~Spec rotation schedule~~ — shipped (PR #180, `scripts/rotate_round.py`; Discord embed on `DISCORD_WEBHOOK_URL`)

---

## Future rounds

- [ ] **Round 004 spec set** — run `python3 scripts/rotate_round.py --close round_001 --new round_004 --metric mass_grams --seeds-base 1000`. Waiting until rounds 1–3 are competitive.
- [ ] **Round 005 spec set** — harder tier or new geometry family (T-bracket, pipe mount). Define new Tier entry in `specs/generator.py` first.

---

## Hardening (low priority)

- ~~Randomized load-case perturbations~~ — shipped (PR #179, seeded by spec_id in `benchmark/fea.py`)
