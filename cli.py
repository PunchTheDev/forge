#!/usr/bin/env python3
"""forge — local benchmark CLI for miners."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent
SPECS_DIR = ROOT / "specs"
ROUNDS_DIR = ROOT / "rounds"
SOTA_DIR = ROOT / "sota"
AGENTS_DIR = ROOT / "agents"

API_BASE = os.environ.get("FORGE_API_URL", "http://143.244.191.193:8000").rstrip("/")
DASHBOARD_URL = os.environ.get("FORGE_DASHBOARD_URL", "http://143.244.191.193:8080")

# ANSI color codes
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _fetch_json(path: str, timeout: int = 6) -> dict | list | None:
    try:
        with urllib.request.urlopen(f"{API_BASE}{path}", timeout=timeout) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


def _fetch_json_with_status(path: str, timeout: int = 6) -> tuple[dict | list | None, int | None]:
    """Like _fetch_json but also returns the HTTP status code.

    Returns (data, status) where status is None if the API is unreachable.
    Useful for distinguishing 404 (resource not found) from network failure.
    """
    try:
        with urllib.request.urlopen(f"{API_BASE}{path}", timeout=timeout) as r:
            return json.loads(r.read()), r.status
    except urllib.error.HTTPError as exc:
        return None, exc.code
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None, None


def _ok(msg: str) -> None:
    print(f"  {GREEN}PASS{RESET}  {msg}")


def _fail(msg: str) -> None:
    print(f"  {RED}FAIL{RESET}  {msg}")


def _warn(msg: str) -> None:
    print(f"  {YELLOW}WARN{RESET}  {msg}")


def _header(title: str) -> None:
    print(f"\n{BOLD}{CYAN}  {title}{RESET}")
    print(f"  {'─' * 64}")


def _fmt_score(score: float, metric: str) -> str:
    """Format a score value with its correct unit."""
    if metric == "stiffness_to_weight":
        return f"{score:.2f} N/(mm·g)"
    if metric == "deflection_mm":
        return f"{score:.4f}mm"
    return f"{score:.2f}g"


# ---------------------------------------------------------------------------
# forge new <name>
# ---------------------------------------------------------------------------

def cmd_new(args: argparse.Namespace) -> int:
    name = args.name
    dest = AGENTS_DIR / name
    if dest.exists():
        print(f"{RED}error:{RESET} agents/{name} already exists", file=sys.stderr)
        return 1

    template = AGENTS_DIR / "template" / "agent.py"
    dest.mkdir(parents=True)
    dest_file = dest / "agent.py"

    if template.exists():
        dest_file.write_bytes(template.read_bytes())
        print(f"  Created agents/{name}/agent.py from template.")
    else:
        # Minimal working scaffold
        dest_file.write_text(
            f'"""Agent: {name}. Implement generate(spec, llm) -> bytes (STEP)."""\n'
            "from __future__ import annotations\n\n"
            "from forge.sdk.llm import LLMClient\n\n\n"
            "def generate(spec: dict, llm: LLMClient) -> bytes:\n"
            "    constraints = spec[\"constraints\"]\n"
            "    # TODO: build geometry and return STEP bytes\n"
            "    raise NotImplementedError\n"
        )
        print(f"  Created agents/{name}/agent.py (minimal scaffold).")

    print(f"  Run:  forge eval agents/{name}/agent.py")
    return 0


# ---------------------------------------------------------------------------
# forge specs
# ---------------------------------------------------------------------------

def cmd_specs(args: argparse.Namespace) -> int:
    round_filter: str | None = getattr(args, "round", None)
    unclaimed_only: bool = getattr(args, "unclaimed", False)

    # Resolve allowed spec IDs from round manifest if --round given
    allowed_ids: set[str] | None = None
    if round_filter:
        round_file = ROUNDS_DIR / f"{round_filter}.json"
        if not round_file.exists():
            print(f"Round '{round_filter}' not found in rounds/.")
            return 1
        round_data = json.loads(round_file.read_text())
        allowed_ids = {e["id"] for e in round_data.get("specs", [])}

    data = _fetch_json("/specs")

    if data:
        if allowed_ids is not None:
            data = [s for s in data if s.get("id") in allowed_ids]

        # Fetch all SOTA records in one call and index by spec_id.
        sota_list = _fetch_json("/sota") or []
        sota_by_id: dict[str, dict] = {r["spec_id"]: r for r in sota_list if isinstance(r, dict) and "spec_id" in r}

        if unclaimed_only:
            data = [s for s in data if s.get("id") not in sota_by_id]

        label_parts = []
        if round_filter:
            label_parts.append(round_filter)
        if unclaimed_only:
            label_parts.append("unclaimed only")
        label = "Specs — " + ", ".join(label_parts) + "  (live)" if label_parts else "Specs  (live)"
        _header(label)

        has_sota = bool(sota_by_id)
        if has_sota:
            print(f"  {'ID':<22} {'TIER':<7} {'MAT':<8} {'LOAD':>8}  {'BASELINE':>14}  {'SOTA':>14}  STATUS")
            print(f"  {'─' * 86}")
        else:
            print(f"  {'ID':<22} {'TIER':<7} {'NAME':<26} {'MAT':<8} {'LOAD':>8}  {'BASELINE':>14}")
            print(f"  {'─' * 96}")

        for s in data:
            sid = s.get("id", "?")
            tier = sid.rsplit("_", 1)[-1] if "_" in sid else "?"
            mat = (s.get("material", "?") or "?")[:7]
            c = s.get("constraints", {})
            load = c.get("load_newtons", 0)
            sc = s.get("scoring", {})
            metric = sc.get("metric", "mass_grams")
            baseline = (
                sc.get("baseline_mass_grams")
                or sc.get("baseline_stiffness_to_weight")
                or sc.get("baseline_deflection_mm")
                or 0
            )
            baseline_str = _fmt_score(baseline, metric) if isinstance(baseline, (int, float)) and baseline else "?"

            if has_sota:
                sota = sota_by_id.get(sid)
                if sota:
                    sota_score = sota.get("score") or sota.get("mass_grams")
                    sota_str = _fmt_score(sota_score, metric) if sota_score is not None else "?"
                    by = sota.get("contributor", "?")[:10]
                    status = f"{RESET}by {by}"
                else:
                    sota_str = "OPEN"
                    status = f"{GREEN}unclaimed{RESET}"
                sota_col = f"{GREEN}{sota_str:<14}{RESET}" if sota is None else f"{sota_str:<14}"
                print(f"  {sid:<22} {tier:<7} {mat:<8} {load:>8.1f}N  {baseline_str:>14}  {sota_col}  {status}")
            else:
                name = s.get("name", "?")[:24]
                print(f"  {sid:<22} {tier:<7} {name:<26} {mat:<8} {load:>8.1f}N  {baseline_str:>14}")

        unclaimed_count = sum(1 for s in data if s.get("id") not in sota_by_id)
        if has_sota and not unclaimed_only:
            total = len(data)
            print(f"\n  {GREEN}{unclaimed_count} unclaimed{RESET} / {total} shown  — run 'forge specs --unclaimed' to filter")
        print()
        return 0

    # Fallback to local files
    spec_files = _all_spec_files()
    if not spec_files:
        print("No specs found locally and API unreachable.")
        return 1

    _warn("API unreachable — showing local specs")
    _header("Specs  (local fallback)")
    print(f"  {'ID':<22} {'TIER':<7} {'NAME':<30} {'MATERIAL':<10} {'LOAD'}")
    print(f"  {'─' * 80}")
    for sf in spec_files:
        try:
            spec = json.loads(sf.read_text())
            sid = spec.get("id", sf.stem)
            tier = sid.rsplit("_", 1)[-1] if "_" in sid else "?"
            name = spec.get("name", "?")[:28]
            mat = spec.get("material", "?")
            load = spec.get("constraints", {}).get("load_newtons", "?")
            print(f"  {sid:<22} {tier:<7} {name:<30} {mat:<10} {load}N")
        except (json.JSONDecodeError, KeyError):
            print(f"  {sf.stem:<16} (parse error)")
    print()
    return 0


# ---------------------------------------------------------------------------
# forge leaderboard
# ---------------------------------------------------------------------------

def _cmd_leaderboard_history(spec_id: str) -> int:
    """Display progressive SOTA improvement timeline for a spec."""
    # Try partial match against known spec IDs from rounds
    all_specs = [f.stem for f in _all_spec_files()]
    matches = [s for s in all_specs if spec_id in s]
    resolved = matches[0] if len(matches) == 1 else spec_id

    sota = _fetch_json(f"/sota/{resolved}")
    history = _fetch_json(f"/sota/{resolved}/history")

    if sota is None and history is None:
        print(f"{RED}error:{RESET} no data for spec '{resolved}' — API unreachable or unknown spec", file=sys.stderr)
        return 1

    metric = (sota or {}).get("score_metric", "mass_grams") if isinstance(sota, dict) else "mass_grams"
    direction = (sota or {}).get("score_direction", "minimize") if isinstance(sota, dict) else "minimize"
    _header(f"SOTA history — {resolved}  ({metric}, {direction})")

    if not history:
        print(f"  No SOTA submissions yet for {resolved}.\n")
        return 0

    print(f"  {'#':<4} {'DATE':<24} {'CONTRIBUTOR':<22} {'SCORE':>14}  IMPROVEMENT")
    print(f"  {'─' * 72}")
    prev: float | None = None
    for i, pt in enumerate(history, 1):
        score = pt.get("score", 0.0)
        contrib = pt.get("contributor", "?")[:20]
        ts = pt.get("submitted_at", "?")[:19].replace("T", " ")
        score_str = _fmt_score(score, metric)
        if prev is None:
            delta_str = "(baseline)"
        else:
            if direction == "maximize":
                pct = (score - prev) / prev * 100
            else:
                pct = (prev - score) / prev * 100
            color = GREEN if pct > 0 else RED
            delta_str = f"{color}+{pct:.2f}%{RESET}"
        print(f"  {i:<4} {ts:<24} {contrib:<22} {score_str:>14}  {delta_str}")
        prev = score

    if isinstance(sota, dict) and sota.get("contributor"):
        print(f"\n  {BOLD}Current SOTA:{RESET} {GREEN}{_fmt_score(sota.get('score', 0), metric)}{RESET}  held by {sota['contributor']}")
    print()
    return 0


def _cmd_leaderboard_agent(contributor: str) -> int:
    """Show a contributor's per-spec standings from the live leaderboard."""
    lb_data = _fetch_json("/leaderboard/overall")
    if not lb_data or not isinstance(lb_data, dict):
        print(f"{YELLOW}API unreachable — no leaderboard data available.{RESET}")
        return 1

    entries = lb_data.get("entries", [])
    # Case-insensitive substring match
    matching = [e for e in entries if contributor.lower() in e.get("contributor", "").lower()]

    if not matching:
        known = [e.get("contributor", "") for e in entries]
        print(f"{RED}error:{RESET} contributor '{contributor}' not found on leaderboard.")
        if known:
            print(f"  Known contributors: {', '.join(known[:8])}")
        return 1

    entry = matching[0]
    contrib_name = entry.get("contributor", contributor)
    overall = entry.get("overall_score", 1.0)
    rank = entry.get("rank", "?")
    wins = entry.get("total_wins", 0)
    total_specs = lb_data.get("total_specs", 0)
    bests: list[dict] = entry.get("best", [])

    _header(f"Agent: {contrib_name}  (rank #{rank})")
    print(f"\n  Overall score: {BOLD}{overall:.4f}{RESET}  ({wins} spec wins, {len(bests)}/{total_specs} entered)")

    if not bests:
        print(f"\n  {YELLOW}No submitted specs yet — open a PR to compete.{RESET}\n")
        return 0

    # Group by round prefix (r01_, r02_, r03_, or other)
    def _round_prefix(spec_id: str) -> str:
        for prefix in ("r01", "r02", "r03"):
            if spec_id.startswith(prefix):
                return prefix
        return "other"

    ROUND_LABEL = {"r01": "Round 001 — Mass", "r02": "Round 002 — Stiffness/Weight", "r03": "Round 003 — Deflection"}

    from collections import defaultdict
    by_round: dict[str, list[dict]] = defaultdict(list)
    for b in sorted(bests, key=lambda x: x.get("spec_id", "")):
        by_round[_round_prefix(b["spec_id"])].append(b)

    print()
    for rk in sorted(by_round):
        label = ROUND_LABEL.get(rk, rk)
        print(f"  {BOLD}{label}{RESET}")
        print(f"  {'SPEC':<24} {'RANK':>6}  {'SCORE':>16}  {'PERCENTILE':>10}")
        print(f"  {'─' * 62}")
        for b in by_round[rk]:
            sid = b.get("spec_id", "?")[:22]
            brank = b.get("rank", "?")
            score = b.get("score", 0.0)
            metric = b.get("score_metric", "mass_grams")
            norm = b.get("normalized_score", 1.0)
            score_str = _fmt_score(score, metric)
            pctile = f"{(1 - norm) * 100:.0f}th"
            rank_color = GREEN if brank == 1 else (YELLOW if brank <= 3 else RESET)
            print(f"  {sid:<24} {rank_color}{brank:>6}{RESET}  {score_str:>16}  {pctile:>10}")
        print()

    # Show unentered specs so the miner knows what's dragging their score down.
    # Fetch active round specs and current SOTAs to show what score to beat.
    entered_ids = {b.get("spec_id") for b in bests}
    rounds_data = _fetch_json("/rounds/active")
    sota_all = _fetch_json("/sota")
    sota_map: dict[str, dict] = {}
    if isinstance(sota_all, list):
        for sr in sota_all:
            if isinstance(sr, dict):
                sota_map[sr.get("spec_id", "")] = sr
    if rounds_data and isinstance(rounds_data, list):
        unentered: list[tuple[str, str, str]] = []  # (round_id, spec_id, metric)
        round_metric: dict[str, str] = {}
        for r in rounds_data:
            round_metric[r["id"]] = r.get("scoring_metric", "mass_grams")
            for s in r.get("specs", []):
                if s["id"] not in entered_ids:
                    unentered.append((r["id"], s["id"], round_metric[r["id"]]))

        if unentered:
            print(f"  {BOLD}{YELLOW}Unentered specs — each scoring 1.0 (worst){RESET}")
            print(f"  {'ROUND':<12} {'SPEC':<24} {'CURRENT SOTA':>16}")
            print(f"  {'─' * 56}")
            for rid, sid, metric in sorted(unentered):
                rk = next((k for k, v in {"r01": "round_001", "r02": "round_002", "r03": "round_003"}.items()
                           if rid == v), rid[:5])
                sota_rec = sota_map.get(sid)
                if sota_rec:
                    sota_score = sota_rec.get("score") or sota_rec.get("mass_grams", 0)
                    sota_str = _fmt_score(sota_score, sota_rec.get("score_metric", metric))
                else:
                    sota_str = f"{YELLOW}unclaimed{RESET}"
                print(f"  {rk:<12} {sid:<24} {sota_str:>16}")
            print()

    print(f"  forge leaderboard --spec <spec_id>   per-spec rankings")
    print(f"  forge leaderboard --history <spec>   SOTA progression")
    print()
    return 0


def cmd_leaderboard(args: argparse.Namespace) -> int:
    spec_filter = getattr(args, "history", None)
    if spec_filter:
        return _cmd_leaderboard_history(spec_filter)

    agent_name = getattr(args, "agent", None)
    if agent_name:
        return _cmd_leaderboard_agent(agent_name)

    spec_id = getattr(args, "spec", None)
    if spec_id:
        return _cmd_leaderboard_spec(spec_id)

    # Default: overall cross-contributor ranking
    lb_data = _fetch_json("/leaderboard/overall")
    rounds_data = _fetch_json("/rounds/active")

    if lb_data and isinstance(lb_data, dict):
        _header("Forge Leaderboard  (live)")

        total_specs = lb_data.get("total_specs", 0)
        entries = lb_data.get("entries", [])

        # Overall contributor rankings
        # overall_score = breadth-normalized mean percentile rank across all active specs.
        # Lower is better; 1.0 = baseline (unentered specs). Primary Gittensor reward metric.
        print(f"\n  {'RANK':<6} {'CONTRIBUTOR':<24} {'SPECS WON':>10}  {'SPECS ENTERED':>14}  {'SCORE':>7}")
        print(f"  {'─' * 66}")
        for e in entries[:20]:
            rank = e.get("rank", "?")
            contrib = e.get("contributor", "?")[:22]
            specs_entered = e.get("specs_entered", 0)
            wins = e.get("total_wins", 0)
            score = e.get("overall_score", 1.0)
            color = GREEN if rank == 1 else RESET
            print(f"  {color}{rank:<6} {contrib:<24} {wins:>10}  {specs_entered:>14}  {score:>7.4f}{RESET}")

        if not entries:
            print(f"  {YELLOW}No submissions yet — be the first!{RESET}")

        # Unclaimed specs summary from active rounds
        if rounds_data and isinstance(rounds_data, list):
            sota_data = _fetch_json("/sota")
            claimed: set[str] = set()
            if isinstance(sota_data, list):
                for r in sota_data:
                    claimed.add(r["spec_id"])

            total_round_specs = sum(len(r.get("specs", [])) for r in rounds_data)
            unclaimed_count = sum(
                1 for r in rounds_data
                for s in r.get("specs", [])
                if s["id"] not in claimed
            )

            print(f"\n  {BOLD}Open Opportunities{RESET}")
            print(f"  {YELLOW}{unclaimed_count}/{total_round_specs} specs unclaimed — any passing submission sets new SOTA{RESET}")
            for r in rounds_data:
                specs = r.get("specs", [])
                round_claimed = sum(1 for s in specs if s["id"] in claimed)
                unclaimed = len(specs) - round_claimed
                metric = r.get("scoring_metric", "?")
                direction = r.get("scoring_direction", "?")
                bar_filled = round_claimed
                bar_empty = len(specs) - round_claimed
                bar = f"{GREEN}{'█' * bar_filled}{YELLOW}{'░' * bar_empty}{RESET}"
                print(f"  {r['id']}  {bar}  {round_claimed}/{len(specs)} claimed  [{metric} {direction}]")

        print()
        print(f"  forge leaderboard --spec <spec_id>    per-spec rankings")
        print(f"  forge leaderboard --history <spec>    SOTA progression")
        print(f"  forge leaderboard --agent <name>      per-spec standings for one contributor")
        print()
        return 0

    print(f"{YELLOW}API unreachable — no leaderboard data available.{RESET}")
    return 1


def _cmd_leaderboard_spec(spec_id: str) -> int:
    """Show per-spec leaderboard and SOTA for a single spec."""
    lb_data = _fetch_json(f"/leaderboard/{spec_id}")
    sota = _fetch_json(f"/sota/{spec_id}")

    if lb_data is None and sota is None:
        print(f"{RED}error:{RESET} spec '{spec_id}' not found or API unreachable.", file=sys.stderr)
        return 1

    _header(f"Spec Leaderboard — {spec_id}")

    if sota and isinstance(sota, dict):
        metric = sota.get("score_metric", "mass_grams")
        score = sota.get("score") or sota.get("mass_grams")
        direction = sota.get("score_direction", "minimize")
        if score is not None:
            elig = _fetch_json(f"/sota/{spec_id}/eligibility?score={score}")
            req_pct = elig.get("required_improvement_pct", 0) if isinstance(elig, dict) else 0
            margin_note = f"  {YELLOW}(beat by ≥{req_pct:.1f}% to claim){RESET}" if req_pct > 0 else ""
            print(f"\n  SOTA: {GREEN}{_fmt_score(score, metric)}{RESET}  ({sota.get('contributor', '?')})  [{direction}]{margin_note}")
        else:
            print(f"\n  {YELLOW}SOTA: unclaimed — any passing submission wins{RESET}")
    else:
        print(f"\n  {YELLOW}SOTA: unclaimed — any passing submission wins{RESET}")

    entries = []
    if isinstance(lb_data, dict):
        entries = lb_data.get("entries", [])
    elif isinstance(lb_data, list):
        entries = lb_data

    if entries:
        metric = entries[0].get("score_metric", "mass_grams")
        print(f"\n  {'RANK':<6} {'CONTRIBUTOR':<24} {'SCORE':>14}  {'VS SOTA':>10}")
        print(f"  {'─' * 58}")
        sota_score = (sota or {}).get("score") or (sota or {}).get("mass_grams")
        sota_dir = (sota or {}).get("score_direction", "minimize")
        for e in entries[:10]:
            rank = e.get("rank", "?")
            contrib = e.get("contributor", "?")[:22]
            score = e.get("score") or e.get("mass_grams", 0)
            sm = e.get("score_metric", metric)
            score_str = _fmt_score(score, sm)
            if sota_score:
                if sota_dir == "maximize":
                    delta_pct = (score - sota_score) / sota_score * 100
                    vs = f"{delta_pct:+.1f}%"
                    color = GREEN if delta_pct >= 0 else YELLOW
                else:
                    delta = score - sota_score
                    vs = f"{delta:+.3g}"
                    color = GREEN if delta <= 0 else YELLOW
            else:
                vs = "first!"
                color = GREEN
            print(f"  {rank:<6} {contrib:<24} {score_str:>14}  {color}{vs:>10}{RESET}")
    else:
        print(f"  {YELLOW}No submissions yet — any passing agent claims SOTA.{RESET}")

    print()
    return 0


# ---------------------------------------------------------------------------
# forge status <agent>
# ---------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> int:
    agent_path = Path(args.agent)
    if not agent_path.exists():
        print(f"{RED}error:{RESET} agent not found: {agent_path}", file=sys.stderr)
        return 1

    use_docker = getattr(args, "docker", False)
    if use_docker and shutil.which("docker") is None:
        print(f"{RED}error:{RESET} docker not found — install Docker Desktop or Engine first", file=sys.stderr)
        return 1

    round_filter: str | None = getattr(args, "round", None)
    if round_filter:
        spec_files = _specs_for_round(round_filter)
        if not spec_files:
            print(f"{RED}error:{RESET} no specs found for round '{round_filter}'", file=sys.stderr)
            return 1
    else:
        spec_files = _all_spec_files()
        if args.spec:
            spec_files = [f for f in spec_files if args.spec in f.name]
    if not spec_files:
        print(f"{RED}error:{RESET} no specs found", file=sys.stderr)
        return 1

    if use_docker:
        rc = _ensure_docker_image()
        if rc != 0:
            return rc

    sota_data = _fetch_json("/sota")
    sota_map: dict = {}
    if isinstance(sota_data, list):
        for r in sota_data:
            sota_map[r["spec_id"]] = r
    elif isinstance(sota_data, dict) and "spec_id" in sota_data:
        sota_map[sota_data["spec_id"]] = sota_data

    _header(f"Status: {agent_path.parent.name}")
    overall_pass = True

    for spec_file in spec_files:
        spec = json.loads(spec_file.read_text())
        spec_id = spec.get("id", spec_file.stem)
        print(f"\n  {BOLD}{spec_id}{RESET}  {spec.get('name', '')}")

        if use_docker:
            result = _run_evaluate_docker(str(agent_path), str(spec_file), verbose=False)
        else:
            result = _run_evaluate(str(agent_path), str(spec_file), verbose=False)

        if not result.get("passed"):
            _fail(f"stage={result.get('stage', '?')}  {result.get('reason', '')[:60]}")
            overall_pass = False
            continue

        mass = result.get("score") or result.get("mass_grams")
        stress = result.get("fea_stress_mpa", "?")
        allowable = result.get("fea_allowable_mpa", "?")
        elapsed = result.get("elapsed_seconds", "?")

        sota = sota_map.get(spec_id, {})
        sota_score = sota.get("score") or sota.get("score_grams") or sota.get("mass_grams")
        sota_metric = sota.get("score_metric", "mass_grams")
        sota_direction = sota.get("score_direction", "minimize")
        result_metric = result.get("score_metric", "mass_grams")

        margin_str = ""
        if sota_score and mass is not None:
            if sota_direction == "maximize":
                delta_pct = (mass - sota_score) / sota_score * 100
                if delta_pct > 0:
                    vs_str = f"{GREEN}beats SOTA by {delta_pct:.1f}%  ({_fmt_score(sota_score, sota_metric)} → {_fmt_score(mass, result_metric)}){RESET}"
                else:
                    vs_str = f"{YELLOW}{abs(delta_pct):.1f}% below SOTA  ({_fmt_score(sota_score, sota_metric)}){RESET}"
            else:
                delta = mass - sota_score
                if delta < 0:
                    vs_str = f"{GREEN}beats SOTA by {abs(delta):.3g}  ({_fmt_score(sota_score, sota_metric)} → {_fmt_score(mass, result_metric)}){RESET}"
                else:
                    vs_str = f"{YELLOW}{delta:.3g} above SOTA  ({_fmt_score(sota_score, sota_metric)}){RESET}"

            # Check margin eligibility against the live decay schedule.
            # Beats SOTA raw ≠ eligible to claim — the margin threshold can block it.
            beats_raw = (
                (sota_direction == "maximize" and mass > sota_score)
                or (sota_direction != "maximize" and mass < sota_score)
            )
            if beats_raw:
                elig = _fetch_json(f"/sota/{spec_id}/eligibility?score={mass}")
                if isinstance(elig, dict):
                    required_pct = elig.get("required_improvement_pct", 0)
                    if elig.get("eligible"):
                        margin_str = f"{GREEN}margin ok  (≥{required_pct:.1f}% required){RESET}"
                    else:
                        margin_str = f"{RED}margin too small  (≥{required_pct:.1f}% required — won't claim SOTA){RESET}"
        elif mass is not None:
            vs_str = "(no live SOTA to compare)"
        else:
            vs_str = ""

        score_str = _fmt_score(mass, result_metric) if mass is not None else "?"
        elapsed_str = f"{elapsed:.1f}s" if isinstance(elapsed, (int, float)) else "?"
        _ok(f"{score_str}  stress={stress}/{allowable} MPa  t={elapsed_str}")
        if vs_str:
            print(f"         {vs_str}")
        if margin_str:
            print(f"         {margin_str}")

    print()
    return 0 if overall_pass else 1


# ---------------------------------------------------------------------------
# forge eval <agent>
# ---------------------------------------------------------------------------

def cmd_eval(args: argparse.Namespace) -> int:
    agent_path = Path(args.agent)
    if not agent_path.exists():
        print(f"{RED}error:{RESET} agent not found: {agent_path}", file=sys.stderr)
        return 1

    use_docker = getattr(args, "docker", False)
    if use_docker and shutil.which("docker") is None:
        print(f"{RED}error:{RESET} docker not found — install Docker Desktop or Engine first", file=sys.stderr)
        return 1

    if getattr(args, "round", None):
        spec_files = _specs_for_round(args.round)
        if not spec_files:
            print(f"{RED}error:{RESET} no specs found for round '{args.round}'", file=sys.stderr)
            return 1
    elif args.all:
        spec_files = _all_spec_files()
    elif args.spec:
        matches = list(SPECS_DIR.glob(f"*{args.spec}*.json"))
        if not matches:
            # Also search round subdirectories
            matches = list(SPECS_DIR.glob(f"**/*{args.spec}*.json"))
        if not matches:
            print(f"{RED}error:{RESET} no spec matching '{args.spec}'", file=sys.stderr)
            return 1
        spec_files = matches[:1]
    else:
        spec_files = sorted(SPECS_DIR.glob("*.json"))

    if not spec_files:
        print(f"{RED}error:{RESET} no specs found in specs/", file=sys.stderr)
        return 1

    if use_docker:
        rc = _ensure_docker_image()
        if rc != 0:
            return rc

    overall_pass = True
    results = []

    for spec_file in spec_files:
        spec = json.loads(spec_file.read_text())
        spec_id = spec.get("id", spec_file.stem)

        if not args.json:
            print(f"\n{'─' * 64}")
            print(f"  spec: {spec_id}  ({spec.get('name', '')})")
            print(f"  agent: {agent_path}")
            print(f"{'─' * 64}")

        if use_docker:
            result = _run_evaluate_docker(str(agent_path), str(spec_file), verbose=not args.json)
        else:
            result = _run_evaluate(str(agent_path), str(spec_file), verbose=not args.json)
        results.append({"spec": spec_id, **result})

        if not result["passed"]:
            overall_pass = False

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))
    elif len(results) > 1:
        _print_summary_table(results)

    # For single-spec runs, show SOTA comparison inline so the miner
    # immediately sees whether their score is competitive.
    if not args.json and len(results) == 1:
        r = results[0]
        if r.get("passed") and r.get("score") is not None:
            spec_id = r["spec"]
            score = r["score"]
            metric = r.get("score_metric", "mass_grams")
            sota, sota_status = _fetch_json_with_status(f"/sota/{spec_id}")
            if sota and isinstance(sota, dict):
                sota_score = sota.get("score") or sota.get("mass_grams")
                sota_dir = sota.get("score_direction", "minimize")
                sota_metric = sota.get("score_metric", metric)
                if sota_score is not None:
                    print(f"  {'─' * 62}")
                    print(f"  Current SOTA: {_fmt_score(sota_score, sota_metric)}  by {sota.get('contributor', '?')}")
                    elig = _fetch_json(f"/sota/{spec_id}/eligibility?score={score}")
                    if isinstance(elig, dict):
                        if elig.get("eligible"):
                            req = elig.get("required_improvement_pct", 0)
                            print(f"  {GREEN}Beats SOTA and meets ≥{req:.1f}% margin — eligible to claim!{RESET}")
                        else:
                            req = elig.get("required_improvement_pct", 0)
                            beats_raw = (sota_dir == "maximize" and score > sota_score) or (sota_dir != "maximize" and score < sota_score)
                            if beats_raw:
                                print(f"  {YELLOW}Beats SOTA raw but margin too small — need ≥{req:.1f}% improvement.{RESET}")
                            else:
                                print(f"  {YELLOW}Does not beat SOTA ({_fmt_score(sota_score, sota_metric)}).{RESET}")
                    print()
            elif sota_status == 404:
                # Spec exists but no submissions yet — any passing entry sets the record.
                print(f"  {'─' * 62}")
                print(f"  {GREEN}No SOTA yet — this submission would set the record!{RESET}")
                print()

    return 0 if overall_pass else 1


# ---------------------------------------------------------------------------
# forge submit
# ---------------------------------------------------------------------------

def cmd_submit(args: argparse.Namespace) -> int:
    _header("Submit to Forge Leaderboard")

    issues = []
    branch = ""

    # Check git
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(ROOT), text=True, stderr=subprocess.DEVNULL
        ).strip()
        commit = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(ROOT), text=True, stderr=subprocess.DEVNULL
        ).strip()
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=str(ROOT), text=True, stderr=subprocess.DEVNULL
        ).strip()
        _ok(f"git branch: {branch}  commit: {commit}")
        _ok(f"remote: {remote}")
    except subprocess.CalledProcessError:
        _fail("not a git repo or no commits")
        issues.append("Initialize a git repo and make at least one commit.")

    if branch == "main":
        _warn("You are on main — submissions should be from a feature branch.")
        issues.append("Create a branch: git checkout -b agents/<your-handle>")

    try:
        subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=str(ROOT), text=True
        )
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=str(ROOT), text=True
        ).strip()
        if dirty:
            _warn("Uncommitted changes — commit everything before submitting.")
            issues.append("Commit all changes: git add <files> && git commit -m '...'")
        else:
            _ok("Working tree clean")
    except subprocess.CalledProcessError:
        pass

    print()
    if issues:
        print(f"  {YELLOW}Fix these before submitting:{RESET}")
        for i, issue in enumerate(issues, 1):
            print(f"    {i}. {issue}")
        print()

    print(f"  {BOLD}Submission steps:{RESET}")
    print("    1. Push your branch:   git push -u origin <branch>")
    print("    2. Open a pull request against the forge repo main branch.")
    print("    3. CI will run eval and post scores as a PR comment.")
    print("    4. A maintainer will review and merge if it passes FEA.")
    print()
    print(f"  API:  {API_BASE}")
    print(f"  Leaderboard:  {DASHBOARD_URL}")
    print()
    return 0 if not issues else 1


# ---------------------------------------------------------------------------
# forge validate  (geometry-only fast check — skips FEA)
# ---------------------------------------------------------------------------

def _run_validate(agent_path: str, spec_path: str, verbose: bool) -> dict:
    """Run agent + geometry validation only (no FEA). Fast local iteration."""
    cmd = [
        sys.executable, "-m", "benchmark.evaluate",
        "--agent", agent_path,
        "--spec", spec_path,
        "--geometry-only",
        "--json",
    ]
    env = os.environ.copy()
    env.setdefault("FORGE_MODEL", "anthropic/claude-haiku-4-5")
    wl_path = ROOT / "config" / "model-whitelist.txt"
    if wl_path.exists():
        wl = ",".join(
            l.strip() for l in wl_path.read_text().splitlines()
            if l.strip() and not l.strip().startswith("#")
        )
    else:
        wl = "anthropic/claude-haiku-4-5,anthropic/claude-3-5-haiku,openai/gpt-4o-mini"
    env.setdefault("FORGE_MODEL_WHITELIST", wl)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), env=env)
    except FileNotFoundError:
        return {"passed": False, "stage": "error", "reason": "benchmark module not found — run from repo root"}

    stdout = proc.stdout.strip()
    result: dict = {}
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                result = json.loads(line)
                break
            except json.JSONDecodeError:
                pass

    if not result and proc.stdout:
        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            result = {"passed": False, "stage": "error", "reason": proc.stdout or proc.stderr}

    if not result:
        result = {"passed": False, "stage": "error", "reason": proc.stderr or "no output"}

    if verbose:
        if result.get("passed"):
            mass = result.get("score")
            elapsed = result.get("elapsed_seconds", "?")
            mass_str = f"{mass:.3g} g" if isinstance(mass, (int, float)) else "?"
            elapsed_str = f"{elapsed:.1f}s" if isinstance(elapsed, (int, float)) else "?"
            _ok(f"geometry ok  mass≈{mass_str}  t={elapsed_str}")
        else:
            stage = result.get("stage", "?")
            reason = result.get("reason", "unknown error")
            _fail(f"stage={stage}")
            print(f"         reason: {reason}")

    return result


def cmd_validate(args: argparse.Namespace) -> int:
    """Geometry-only check — runs agent and validates STEP geometry, skips FEA."""
    agent_path = Path(args.agent)
    if not agent_path.exists():
        print(f"{RED}error:{RESET} agent not found: {agent_path}", file=sys.stderr)
        return 1

    if getattr(args, "round", None):
        spec_files = _specs_for_round(args.round)
        if not spec_files:
            print(f"{RED}error:{RESET} no specs found for round '{args.round}'", file=sys.stderr)
            return 1
    elif getattr(args, "all", False):
        spec_files = _all_spec_files()
    elif args.spec:
        matches = list(SPECS_DIR.glob(f"*{args.spec}*.json"))
        if not matches:
            matches = list(SPECS_DIR.glob(f"**/*{args.spec}*.json"))
        if not matches:
            print(f"{RED}error:{RESET} no spec matching '{args.spec}'", file=sys.stderr)
            return 1
        spec_files = matches[:1]
    else:
        spec_files = sorted(SPECS_DIR.glob("*.json"))

    if not spec_files:
        print(f"{RED}error:{RESET} no specs found in specs/", file=sys.stderr)
        return 1

    use_docker = getattr(args, "docker", False)
    if use_docker:
        rc = _ensure_docker_image()
        if rc != 0:
            return rc

    overall_pass = True
    results = []

    for spec_file in spec_files:
        spec = json.loads(spec_file.read_text())
        spec_id = spec.get("id", spec_file.stem)

        if not args.json:
            print(f"\n{'─' * 64}")
            print(f"  spec: {spec_id}  ({spec.get('name', '')})")
            mode_note = f"  {YELLOW}[Docker — geometry only, no FEA]{RESET}" if use_docker else f"  {CYAN}[geometry only — no FEA]{RESET}"
            print(f"  agent: {agent_path}{mode_note}")
            print(f"{'─' * 64}")

        if use_docker:
            result = _run_evaluate_docker(str(agent_path), str(spec_file), verbose=not args.json, geometry_only=True)
        else:
            result = _run_validate(str(agent_path), str(spec_file), verbose=not args.json)
        results.append({"spec": spec_id, **result})

        if not result["passed"]:
            overall_pass = False

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))
    elif len(results) > 1:
        _print_summary_table(results)

    return 0 if overall_pass else 1


# ---------------------------------------------------------------------------
# forge rounds
# ---------------------------------------------------------------------------

def cmd_rounds(args: argparse.Namespace) -> int:
    round_files = sorted(ROUNDS_DIR.glob("*.json")) if ROUNDS_DIR.exists() else []
    if not round_files:
        print("No rounds found in rounds/.")
        return 1

    _header("Competition Rounds")
    for rf in round_files:
        try:
            round_data = json.loads(rf.read_text())
        except json.JSONDecodeError:
            print(f"  {RED}error:{RESET} could not parse {rf.name}")
            continue

        rid = round_data.get("id", rf.stem)
        name = round_data.get("name", "?")
        status = round_data.get("status", "unknown")
        starts = round_data.get("starts", "?")
        ends = round_data.get("ends") or "ongoing"
        metric = round_data.get("scoring_metric", "?")
        specs = round_data.get("specs", [])

        status_color = GREEN if status == "active" else YELLOW
        print(f"\n  {BOLD}{rid}{RESET}  {status_color}[{status}]{RESET}")
        print(f"  {name}")
        print(f"  Period: {starts} → {ends}  |  Metric: {metric}  |  Specs: {len(specs)}")
        print()

        tiers: dict[str, list[str]] = {}
        for s in specs:
            tier = s.get("tier", "unknown")
            tiers.setdefault(tier, []).append(s["id"])

        for tier in ("easy", "medium", "hard", "unknown"):
            ids = tiers.get(tier)
            if not ids:
                continue
            label = f"{tier.capitalize():<8}"
            print(f"    {CYAN}{label}{RESET}  {', '.join(ids)}")

    print()

    if args.list_specs and round_files:
        active = [r for r in round_files
                  if json.loads(r.read_text()).get("status") == "active"]
        if active:
            round_data = json.loads(active[0].read_text())
            print(f"  Active round: {round_data['id']} — {len(round_data.get('specs', []))} specs")
            print(f"  Run: forge eval agents/<your-agent>/agent.py --round {round_data['id']}")
            print()

    return 0


# ---------------------------------------------------------------------------
# forge check-deps
# ---------------------------------------------------------------------------

def cmd_check_deps(args: argparse.Namespace) -> int:
    _header("Dependency check")

    # --- Docker path ---
    print(f"  {BOLD}Option A — Docker (recommended){RESET}")
    docker_found = bool(shutil.which("docker"))
    if docker_found:
        try:
            proc = subprocess.run(
                ["docker", "--version"], capture_output=True, text=True, timeout=5
            )
            version = (proc.stdout or proc.stderr).strip().splitlines()[0][:40]
            _ok(f"  {'docker':<22} {version}")
        except Exception:
            _ok(f"  {'docker':<22} found")

        # Check whether the pre-built eval image is already present locally.
        try:
            proc = subprocess.run(
                ["docker", "image", "inspect", "forge-eval:latest"],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode == 0:
                _ok(f"  {'forge-eval image':<22} cached locally")
            else:
                _warn(f"  {'forge-eval image':<22} not pulled — first run will pull from GHCR (~1 min)")
        except Exception:
            _warn(f"  {'forge-eval image':<22} status unknown")
    else:
        _fail(f"  {'docker':<22} NOT FOUND — install Docker to use Option A")

    print(f"\n  {BOLD}Option B — Native toolchain{RESET}")
    native_ok = True
    checks = [
        ("python", ["python3", "--version"]),
        ("ccx (CalculiX)", ["ccx", "-v"]),
        ("gmsh", ["gmsh", "--version"]),
    ]

    for name, cmd in checks:
        found = shutil.which(cmd[0])
        if found:
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                if proc.returncode == 0:
                    version = (proc.stdout or proc.stderr).strip().splitlines()[0][:40]
                    _ok(f"  {name:<22} {version}")
                else:
                    err = (proc.stderr or proc.stdout).strip().splitlines()[0][:60]
                    _fail(f"  {name:<22} found but broken — {err}")
                    native_ok = False
            except Exception:
                _ok(f"  {name:<22} (found at {found})")
        else:
            _fail(f"  {name:<22} NOT FOUND")
            native_ok = False

    try:
        subprocess.run(
            [sys.executable, "-c", "import OCC.Core.BRep; print('ok')"],
            check=True, capture_output=True, timeout=30, cwd=str(ROOT)
        )
        _ok(f"  {'OCP (build123d/OCC)':<22} importable")
    except subprocess.CalledProcessError:
        _fail(f"  {'OCP (build123d/OCC)':<22} import failed — run: pip install build123d")
        native_ok = False
    except subprocess.TimeoutExpired:
        _warn(f"  {'OCP (build123d/OCC)':<22} import timed out (slow cold start is normal)")

    print()
    if docker_found:
        print(f"  {GREEN}Docker available — run evals with: forge eval --docker agents/<your-agent>/agent.py{RESET}")
        if not native_ok:
            print(f"  {YELLOW}(native toolchain incomplete — Option A only){RESET}")
    elif native_ok:
        print(f"  {GREEN}Native toolchain ready — run evals with: forge eval agents/<your-agent>/agent.py{RESET}")
    else:
        print(f"  {RED}Neither Docker nor native toolchain found.{RESET}")
        print(f"  Install Docker (recommended): https://docs.docker.com/get-docker/")
        print(f"  Or native toolchain: see README.md")
    print()
    return 0 if (docker_found or native_ok) else 1


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_evaluate(agent_path: str, spec_path: str, verbose: bool) -> dict:
    cmd = [
        sys.executable, "-m", "benchmark.evaluate",
        "--agent", agent_path,
        "--spec", spec_path,
        "--json",
    ]
    # Inherit environment; supply defaults so LLM agents work without extra setup.
    env = os.environ.copy()
    env.setdefault("FORGE_MODEL", "anthropic/claude-haiku-4-5")
    wl_path = ROOT / "config" / "model-whitelist.txt"
    if wl_path.exists():
        wl = ",".join(
            l.strip() for l in wl_path.read_text().splitlines()
            if l.strip() and not l.strip().startswith("#")
        )
    else:
        wl = "anthropic/claude-haiku-4-5,anthropic/claude-3-5-haiku,openai/gpt-4o-mini"
    env.setdefault("FORGE_MODEL_WHITELIST", wl)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), env=env)
    except FileNotFoundError:
        return {"passed": False, "stage": "error", "reason": "benchmark module not found — run from repo root"}

    stdout = proc.stdout.strip()
    result: dict = {}
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                result = json.loads(line)
                break
            except json.JSONDecodeError:
                pass

    if not result and proc.stdout:
        try:
            result = json.loads(proc.stdout)
        except json.JSONDecodeError:
            result = {"passed": False, "stage": "error", "reason": proc.stdout or proc.stderr}

    if not result:
        result = {"passed": False, "stage": "error", "reason": proc.stderr or "no output"}

    if verbose:
        if result.get("passed"):
            score = result.get("score", "?")
            stress = result.get("fea_stress_mpa", "?")
            allowable = result.get("fea_allowable_mpa", "?")
            elapsed = result.get("elapsed_seconds", "?")
            metric = result.get("score_metric", "mass_grams")
            score_str = _fmt_score(score, metric) if isinstance(score, (int, float)) else str(score)
            elapsed_str = f"{elapsed:.1f}s" if isinstance(elapsed, (int, float)) else str(elapsed)
            _ok(f"score={score_str}  stress={stress}/{allowable} MPa  t={elapsed_str}")
        else:
            stage = result.get("stage", "?")
            reason = result.get("reason", "unknown error")
            _fail(f"stage={stage}")
            print(f"         reason: {reason}")

    return result


DOCKER_IMAGE = "forge-eval:latest"
DOCKER_REMOTE = "ghcr.io/punchthedev/forge-eval:latest"
DOCKER_TIMEOUT = 25 * 60  # 25 minutes — same cap as CI


def _ensure_docker_image() -> int:
    """Ensure forge-eval:latest is available locally.

    Tries pulling from GHCR first (fast, pre-built). Falls back to a local
    build if the pull fails (e.g. no internet, private network).
    """
    check = subprocess.run(
        ["docker", "image", "inspect", DOCKER_IMAGE],
        capture_output=True,
    )
    if check.returncode == 0:
        return 0  # image already present

    print(f"  {CYAN}pulling forge-eval image from GHCR…{RESET}")
    pull = subprocess.run(
        ["docker", "pull", DOCKER_REMOTE],
    )
    if pull.returncode == 0:
        # Tag the pulled image as the local name the rest of the code expects.
        subprocess.run(
            ["docker", "tag", DOCKER_REMOTE, DOCKER_IMAGE],
            capture_output=True,
        )
        return 0

    print(f"  {YELLOW}GHCR pull failed — falling back to local build (~5 min)…{RESET}")
    build = subprocess.run(
        ["docker", "build", "-t", DOCKER_IMAGE, str(ROOT)],
    )
    if build.returncode != 0:
        print(f"{RED}error:{RESET} docker build failed (see output above)", file=sys.stderr)
        return 1
    return 0


def _run_evaluate_docker(agent_path: str, spec_path: str, verbose: bool, geometry_only: bool = False) -> dict:
    """Run the eval inside the forge-eval Docker container (mirrors CI behaviour).

    Set geometry_only=True to skip FEA — same fast path as forge validate but in Docker.
    """
    import uuid

    workspace = str(ROOT)
    agent_rel = str(Path(agent_path).resolve().relative_to(ROOT))
    spec_rel = str(Path(spec_path).resolve().relative_to(ROOT))

    wl_path = ROOT / "config" / "model-whitelist.txt"
    if wl_path.exists():
        wl = ",".join(
            l.strip() for l in wl_path.read_text().splitlines()
            if l.strip() and not l.strip().startswith("#")
        )
    else:
        wl = "anthropic/claude-haiku-4-5,anthropic/claude-3-5-haiku,openai/gpt-4o-mini"

    llm_key = os.environ.get("FORGE_LLM_KEY", os.environ.get("OPENROUTER_KEY", ""))
    model = os.environ.get("FORGE_MODEL", "anthropic/claude-haiku-4-5")

    container_name = f"forge-eval-local-{uuid.uuid4().hex[:8]}"
    cmd = [
        "docker", "run", "--rm",
        "--name", container_name,
        "--security-opt", "no-new-privileges",
        "--cap-drop", "ALL",
        "--pids-limit", "256",
        "--memory", "4g",
        "--cpus", "2",
        "-e", f"FORGE_LLM_KEY={llm_key}",
        "-e", f"FORGE_MODEL={model}",
        "-e", f"FORGE_MODEL_WHITELIST={wl}",
        "-v", f"{workspace}:/forge",
        DOCKER_IMAGE,
        "--agent", f"/forge/{agent_rel}",
        "--spec", f"/forge/{spec_rel}",
        "--json",
    ]
    if geometry_only:
        cmd.append("--geometry-only")

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=DOCKER_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", container_name], capture_output=True)
        return {"passed": False, "stage": "error", "reason": f"eval timed out after {DOCKER_TIMEOUT // 60} minutes"}

    stdout = proc.stdout.strip()
    result: dict = {}
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                result = json.loads(line)
                break
            except json.JSONDecodeError:
                pass

    if not result and stdout:
        try:
            result = json.loads(stdout)
        except json.JSONDecodeError:
            stderr_tail = proc.stderr.strip()[-300:] if proc.stderr.strip() else ""
            hint = f" | stderr: {stderr_tail}" if stderr_tail else ""
            result = {"passed": False, "stage": "error", "reason": f"{stdout[:120]}{hint}"}

    if not result:
        stderr_tail = proc.stderr.strip()[-300:] if proc.stderr.strip() else ""
        result = {"passed": False, "stage": "error", "reason": stderr_tail or "no output from container"}

    if verbose:
        if result.get("passed"):
            score = result.get("score", "?")
            stress = result.get("fea_stress_mpa", "?")
            allowable = result.get("fea_allowable_mpa", "?")
            elapsed = result.get("elapsed_seconds", "?")
            metric = result.get("score_metric", "mass_grams")
            score_str = _fmt_score(score, metric) if isinstance(score, (int, float)) else str(score)
            elapsed_str = f"{elapsed:.1f}s" if isinstance(elapsed, (int, float)) else str(elapsed)
            _ok(f"score={score_str}  stress={stress}/{allowable} MPa  t={elapsed_str}")
        else:
            stage = result.get("stage", "?")
            reason = result.get("reason", "unknown error")
            _fail(f"stage={stage}")
            print(f"         reason: {reason}")

    return result


def _print_summary_table(results: list[dict]) -> None:
    print(f"\n{'─' * 64}")
    print(f"  {'SPEC':<20} {'STATUS':<8} {'SCORE':>8}  NOTES")
    print(f"{'─' * 64}")
    for r in results:
        spec = r.get("spec", "?")
        passed = r.get("passed", False)
        status_str = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        metric = r.get("score_metric", "mass_grams")
        score = _fmt_score(r["score"], metric) if passed and r.get("score") else "—"
        reason = "" if passed else r.get("reason", "")[:30]
        print(f"  {spec:<20} {status_str}     {score:>8}  {reason}")
    print(f"{'─' * 64}\n")


# ---------------------------------------------------------------------------
# Round helpers
# ---------------------------------------------------------------------------

def _all_spec_files() -> list[Path]:
    """Return all spec JSON files: top-level + all round subdirectories."""
    files = sorted(SPECS_DIR.glob("*.json"))
    files += sorted(SPECS_DIR.glob("**/*.json"))
    # deduplicate while preserving order
    seen: set[Path] = set()
    result = []
    for f in files:
        if f not in seen:
            seen.add(f)
            result.append(f)
    return result


def _specs_for_round(round_id: str) -> list[Path]:
    """Return spec files for a named round, resolving paths from round manifest."""
    round_file = ROUNDS_DIR / f"{round_id}.json"
    if not round_file.exists():
        return []
    try:
        data = json.loads(round_file.read_text())
    except json.JSONDecodeError:
        return []

    files = []
    for entry in data.get("specs", []):
        p = ROOT / entry["file"]
        if p.exists():
            files.append(p)
    return files


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

HELP_TEXT = f"""{BOLD}{CYAN}  forge — Parametric CAD Benchmark CLI{RESET}

  {BOLD}Commands:{RESET}
    {GREEN}forge new <name>{RESET}               Scaffold a new agent in agents/<name>/
    {GREEN}forge eval <agent>{RESET}             Run full benchmark locally (geometry + FEA)
    {GREEN}forge validate <agent>{RESET}         Geometry-only check — fast, no FEA
    {GREEN}forge status <agent>{RESET}           Eval and compare against live SOTA
    {GREEN}forge specs{RESET}                    List all specs with current SOTA state
    {GREEN}forge specs --unclaimed{RESET}        Show only specs with no current leader
    {GREEN}forge rounds{RESET}                   List competition rounds and their spec sets
    {GREEN}forge leaderboard{RESET}              Overall contributor rankings + unclaimed spec summary
    {GREEN}forge leaderboard --spec <id>{RESET}  Per-spec ranking and SOTA for one spec
    {GREEN}forge leaderboard --agent <name>{RESET} Per-spec standings for a contributor
    {GREEN}forge submit{RESET}                   Validate git and print submission guide
    {GREEN}forge check-deps{RESET}               Verify CalculiX, gmsh, OCP are installed

  {BOLD}Eval options:{RESET}
    --spec ID      Run against one spec (partial match: 001, bracket, ...)
    --round ID     Run against all specs in a competition round
    --all          Run against all specs including round subdirectories
    --docker       Run inside Docker container (mirrors CI; no local OCP/ccx needed)
    --json         Output raw JSON

  {BOLD}Environment:{RESET}
    FORGE_API_URL       Override API base (default: {API_BASE})
    FORGE_DASHBOARD_URL Override dashboard URL (default: {DASHBOARD_URL})

  {BOLD}Examples:{RESET}
    forge new my-agent
    forge validate agents/my-agent/agent.py --spec r01_001_easy
    forge eval agents/my-agent/agent.py --spec r01_001_easy
    forge eval agents/my-agent/agent.py --round round_001
    forge rounds
    forge status agents/my-agent/agent.py
    forge leaderboard
"""


def cmd_ingest(args: argparse.Namespace) -> int:
    """forge ingest — pull Thingiverse things and generate Forge specs."""
    try:
        from catalog.ingest import ingest
    except ImportError as exc:
        _fail(f"catalog module not importable: {exc}")
        return 1

    api_key = os.environ.get("THINGIVERSE_KEY")
    if not api_key:
        _fail("THINGIVERSE_KEY not set. Get a key at https://www.thingiverse.com/developers")
        return 1

    _header(f"Thingiverse ingest — {args.n} specs → {args.out_dir}")
    ingest(n=args.n, out_dir=args.out_dir, seed=args.seed, scoring_metric=args.metric, dry_run=args.dry_run)
    return 0


def main() -> None:
    if len(sys.argv) == 1:
        print(HELP_TEXT)
        sys.exit(0)

    parser = argparse.ArgumentParser(prog="forge", add_help=True)
    sub = parser.add_subparsers(dest="command", metavar="command")

    p_new = sub.add_parser("new", help="Scaffold a new agent")
    p_new.add_argument("name", help="Agent name (folder will be agents/<name>/)")
    p_new.set_defaults(func=cmd_new)

    p_eval = sub.add_parser("eval", help="Run benchmark against an agent locally")
    p_eval.add_argument("agent", help="Path to agent.py")
    p_eval.add_argument("--spec", metavar="ID", help="Spec ID or partial name")
    p_eval.add_argument("--round", metavar="ID", help="Run all specs in a competition round")
    p_eval.add_argument("--all", action="store_true", help="Run against all specs including round subdirs")
    p_eval.add_argument("--docker", action="store_true", help="Run inside Docker (mirrors CI; builds image on first use)")
    p_eval.add_argument("--json", action="store_true", help="Output JSON")
    p_eval.set_defaults(func=cmd_eval)

    p_validate = sub.add_parser("validate", help="Geometry-only check — fast local feedback, no FEA")
    p_validate.add_argument("agent", help="Path to agent.py")
    p_validate.add_argument("--spec", metavar="ID", help="Spec ID or partial name")
    p_validate.add_argument("--round", metavar="ID", help="Run all specs in a competition round")
    p_validate.add_argument("--all", action="store_true", help="Run against all specs including round subdirs")
    p_validate.add_argument("--json", action="store_true", help="Output JSON")
    p_validate.add_argument("--docker", action="store_true", help="Run inside forge-eval Docker container (no local OCP needed)")
    p_validate.set_defaults(func=cmd_validate)

    p_status = sub.add_parser("status", help="Eval and compare against live SOTA")
    p_status.add_argument("agent", help="Path to agent.py")
    p_status.add_argument("--spec", metavar="ID", help="Limit to one spec")
    p_status.add_argument("--round", metavar="ID", help="Limit to specs in one round")
    p_status.add_argument("--docker", action="store_true", help="Run eval in Docker (no local OCP/CalculiX needed)")
    p_status.set_defaults(func=cmd_status)

    p_specs = sub.add_parser("specs", help="List available problem specs")
    p_specs.add_argument("--round", metavar="ID", help="Filter to specs in one round (e.g. round_001)")
    p_specs.add_argument("--unclaimed", action="store_true", help="Show only specs with no current SOTA")
    p_specs.set_defaults(func=cmd_specs)

    p_rounds = sub.add_parser("rounds", help="List competition rounds and spec sets")
    p_rounds.add_argument("--list-specs", action="store_true", help="Show specs for active round")
    p_rounds.set_defaults(func=cmd_rounds)

    p_lb = sub.add_parser("leaderboard", help="Show current SOTA scores")
    p_lb.add_argument("--spec", metavar="SPEC_ID", help="Per-spec leaderboard for one spec")
    p_lb.add_argument("--history", metavar="SPEC_ID", help="Show SOTA progression for a spec")
    p_lb.add_argument("--agent", metavar="NAME", help="Per-spec standings for a contributor")
    p_lb.set_defaults(func=cmd_leaderboard)

    p_submit = sub.add_parser("submit", help="Validate git setup and print submission guide")
    p_submit.set_defaults(func=cmd_submit)

    p_deps = sub.add_parser("check-deps", help="Verify local dependencies are installed")
    p_deps.set_defaults(func=cmd_check_deps)

    p_ingest = sub.add_parser("ingest", help="Ingest problem specs from Thingiverse")
    p_ingest.add_argument("--n", type=int, default=50, help="Number of specs to generate")
    p_ingest.add_argument("--out-dir", type=Path, default=Path("specs/catalog/"), metavar="DIR")
    p_ingest.add_argument("--seed", type=int, default=0)
    p_ingest.add_argument("--metric", choices=["mass_grams", "stiffness_to_weight", "deflection_mm"], default="mass_grams")
    p_ingest.add_argument("--dry-run", action="store_true", help="Preview without writing")
    p_ingest.set_defaults(func=cmd_ingest)

    args = parser.parse_args()
    if not args.command:
        print(HELP_TEXT)
        sys.exit(0)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
