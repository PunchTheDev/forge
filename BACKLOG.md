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

---

## Dashboard UX rehaul backlog (3-pillars: Beautiful / Seamless / Understandable instantly)

Status: in progress — see forge-dashboard PRs #85+

### Done this session
- [x] Round page crash (hooks violation + vite chunk split) — PR #85
- [x] Playground redesign: Problem Explorer, auto-load spec, dynamic sample output — PR #86
- [x] SOTA code surfaced on problem detail — PR #86
- [x] `[easy]` stripped from h1 — PR #86
- [x] Rankings "0.0=best / 1.0=worst" clarity — PR #86
- [x] SpecDiagram arrow marker ID collision — PR #86
- [x] Material tooltips (density + key property) — PR #86
- [x] Load shows N + kg equivalent — PR #86
- [x] SpecDiagram build volume dims: `190×90mm build vol.` label, `←78mm arm→` — PR #88
- [x] Rankings: scoring formula deduped, `active specs` → `active problems`, #1 agent always green — PR #88
- [x] WebGL crash (headless/no-GPU): `StepViewerBoundary` catches and falls back to SpecDiagram — PR #88
- [x] `/guide` and `/playground` routes now set correct `document.title` — PR #88
- [x] Playground curl command: `&apos;` entity → actual quote chars — PR #88
- [x] SotaChart y-axis label with metric units — PR #88
- [x] "Be the first to compete" CTA now context-aware when agents exist — PR #88

### P1 — remaining high-impact
- [ ] **Terminology "spec" still used in Guide** — guide uses "spec" ~24× vs "problem" 1×; CLI commands use `--spec` (correct). Guide intro should define the distinction: "spec" = the technical JSON; "problem" = what you're competing on. Currently undefined.
- [ ] **Category icons unexplained** — `⊕` for Stiffness/Weight is opaque. Either add a tooltip on hover explaining "Stiffness-to-weight ratio: N·mm per gram", or replace with a clearer symbol.
- [ ] **"open" vs "unclaimed" inconsistency** — sidebar shows "open", category page shows "unclaimed". Pick one: "open" is better UX ("open" implies you can claim it), "unclaimed" is used in the API filter. Use "open" in UI everywhere.
- [ ] **Unentered spec score tooltip** — `each scores 1.0` label on agent detail has tooltip but no visual indicator it's hoverable; newcomers miss it.
- [ ] **Guide on mobile** — TOC is `hidden lg:block`; sub-1024px users get a flat wall of text with no jump navigation. Make TOC available at smaller breakpoints or add a collapsible mobile menu.

### P2 — polish
- [ ] **SOTA chart y-axis label** — values show cleanly but no axis title ("mass (g)", "stiffness (N/mm·g)", etc.)
- [ ] **`1 agent competing` hero stat** — reframe empty state as opportunity ("42 problems up for grabs")
- [ ] **Pill badges on home look clickable** — "Gittensor SN74", "Open Competition" → de-emphasize so they don't compete with CTA buttons
- [ ] **SF badge tooltip on spec header** — `SF 1.5×` badge has no tooltip explaining "Safety factor: yield / SF = allowable stress"
- [ ] **`sotaMass` param name in SpecCard** — stale for non-mass specs; rename to `sotaScore`
