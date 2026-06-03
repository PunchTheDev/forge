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
            '"""Agent: {name}. Implement generate(spec) -> bytes (STEP)."""\n'
            "from __future__ import annotations\n\n\n"
            "def generate(spec: dict) -> bytes:\n"
            "    constraints = spec[\"constraints\"]\n"
            "    # TODO: build geometry and return STEP bytes\n"
            "    raise NotImplementedError\n"
        )
        print(f"  Created agents/{name}/agent.py (minimal scaffold).")

    print(f"  Run:  python cli.py eval agents/{name}/agent.py")
    return 0


# ---------------------------------------------------------------------------
# forge specs
# ---------------------------------------------------------------------------

def cmd_specs(args: argparse.Namespace) -> int:
    round_filter: str | None = getattr(args, "round", None)

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
        label = f"Specs — {round_filter}  (live)" if round_filter else "Specs  (live)"
        _header(label)
        print(f"  {'ID':<20} {'NAME':<28} {'MATERIAL':<12} {'LOAD':>8}  {'BUILD VOL (mm)':>18}  {'BASELINE':>10}")
        print(f"  {'─' * 100}")
        for s in data:
            sid = s.get("id", "?")[:18]
            name = s.get("name", "?")[:26]
            mat = s.get("material", "?")[:10]
            c = s.get("constraints", {})
            load = c.get("load_newtons", "?")
            bv = c.get("build_volume_mm", [])
            bv_str = f"{bv[0]:.0f}x{bv[1]:.0f}x{bv[2]:.0f}" if len(bv) == 3 else "?"
            sc = s.get("scoring", {})
            metric = sc.get("metric", "mass_grams")
            baseline = (
                sc.get("baseline_mass_grams")
                or sc.get("baseline_stiffness_to_weight")
                or sc.get("baseline_deflection_mm")
                or "?"
            )
            baseline_str = _fmt_score(baseline, metric) if isinstance(baseline, (int, float)) else "?"
            print(f"  {sid:<20} {name:<28} {mat:<12} {load:>8}N  {bv_str:>18}  {baseline_str:>10}")
        print()
        return 0

    # Fallback to local files
    spec_files = _all_spec_files()
    if not spec_files:
        print("No specs found locally and API unreachable.")
        return 1

    _warn("API unreachable — showing local specs")
    _header("Specs  (local fallback)")
    print(f"  {'ID':<16} {'NAME':<30} {'MATERIAL':<10} {'LOAD'}")
    print(f"  {'─' * 72}")
    for sf in spec_files:
        try:
            spec = json.loads(sf.read_text())
            sid = spec.get("id", sf.stem)
            name = spec.get("name", "?")[:28]
            mat = spec.get("material", "?")
            load = spec.get("constraints", {}).get("load_newtons", "?")
            print(f"  {sid:<16} {name:<30} {mat:<10} {load}N")
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


def cmd_leaderboard(args: argparse.Namespace) -> int:
    spec_filter = getattr(args, "history", None)
    if spec_filter:
        return _cmd_leaderboard_history(spec_filter)

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
        print(f"\n  {'RANK':<6} {'CONTRIBUTOR':<24} {'SPECS WON':>10}  {'SPECS ENTERED':>14}  {'AVG SCORE':>10}")
        print(f"  {'─' * 68}")
        for e in entries[:20]:
            rank = e.get("rank", "?")
            contrib = e.get("contributor", "?")[:22]
            specs_entered = e.get("specs_entered", 0)
            wins = e.get("total_wins", 0)
            avg = e.get("avg_normalized_score", 0)
            color = GREEN if rank == 1 else RESET
            print(f"  {color}{rank:<6} {contrib:<24} {wins:>10}  {specs_entered:>14}  {avg:>10.3f}{RESET}")

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
        print(f"  forge leaderboard --spec <spec_id>   per-spec rankings")
        print(f"  forge leaderboard --history <spec>   SOTA progression")
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
            print(f"\n  SOTA: {GREEN}{_fmt_score(score, metric)}{RESET}  ({sota.get('contributor', '?')})  [{direction}]")
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

    spec_files = _all_spec_files()
    if args.spec:
        spec_files = [f for f in spec_files if args.spec in f.name]
    if not spec_files:
        print(f"{RED}error:{RESET} no specs found", file=sys.stderr)
        return 1

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
        elif mass is not None:
            vs_str = "(no live SOTA to compare)"
        else:
            vs_str = ""

        score_str = _fmt_score(mass, result_metric) if mass is not None else "?"
        elapsed_str = f"{elapsed:.1f}s" if isinstance(elapsed, (int, float)) else "?"
        _ok(f"{score_str}  stress={stress}/{allowable} MPa  t={elapsed_str}")
        if vs_str:
            print(f"         {vs_str}")

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

    overall_pass = True
    results = []

    for spec_file in spec_files:
        spec = json.loads(spec_file.read_text())
        spec_id = spec.get("id", spec_file.stem)

        print(f"\n{'─' * 64}")
        print(f"  spec: {spec_id}  ({spec.get('name', '')})")
        print(f"  agent: {agent_path}")
        print(f"{'─' * 64}")

        result = _run_evaluate(str(agent_path), str(spec_file), verbose=not args.json)
        results.append({"spec": spec_id, **result})

        if not result["passed"]:
            overall_pass = False

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))
    elif len(results) > 1:
        _print_summary_table(results)

    return 0 if overall_pass else 1


# ---------------------------------------------------------------------------
# forge submit
# ---------------------------------------------------------------------------

def cmd_submit(args: argparse.Namespace) -> int:
    _header("Submit to Forge Leaderboard")

    issues = []

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
    print(f"  Leaderboard:  {API_BASE}/leaderboard")
    print()
    return 0 if not issues else 1


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
            print(f"  Run: python cli.py eval agents/<your-agent>/agent.py --round {round_data['id']}")
            print()

    return 0


# ---------------------------------------------------------------------------
# forge check-deps
# ---------------------------------------------------------------------------

def cmd_check_deps(args: argparse.Namespace) -> int:
    _header("Dependency check")

    ok = True
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
                version = (proc.stdout or proc.stderr).strip().splitlines()[0][:40]
                _ok(f"{name:<24} {version}")
            except Exception:
                _ok(f"{name:<24} (found at {found})")
        else:
            _fail(f"{name:<24} NOT FOUND")
            ok = False

    print(f"  {'─' * 64}")
    try:
        subprocess.run(
            [sys.executable, "-c", "import OCC.Core.BRep; print('ok')"],
            check=True, capture_output=True, timeout=30, cwd=str(ROOT)
        )
        _ok(f"{'OCP (build123d/OCC)':<24} importable")
    except subprocess.CalledProcessError:
        _fail(f"{'OCP (build123d/OCC)':<24} import failed — run: pip install build123d")
        ok = False
    except subprocess.TimeoutExpired:
        _warn(f"{'OCP (build123d/OCC)':<24} import timed out (slow cold start is normal)")

    print()
    if ok:
        print(f"  {GREEN}All dependencies found. Ready to run evals locally.{RESET}")
    else:
        print(f"  {RED}Some dependencies missing. See README.md for install instructions.{RESET}")
        print("  Or run evals via Docker: see Dockerfile")
    print()
    return 0 if ok else 1


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
    env.setdefault(
        "FORGE_MODEL_WHITELIST",
        "anthropic/claude-haiku-4-5,anthropic/claude-3-5-haiku,openai/gpt-4o-mini",
    )
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
    {GREEN}forge eval <agent>{RESET}             Run benchmark locally against all specs
    {GREEN}forge status <agent>{RESET}           Eval and compare against live SOTA
    {GREEN}forge specs{RESET}                    List all problem specs (live API + local)
    {GREEN}forge rounds{RESET}                   List competition rounds and their spec sets
    {GREEN}forge leaderboard{RESET}              Overall contributor rankings + unclaimed spec summary
    {GREEN}forge leaderboard --spec <id>{RESET}  Per-spec ranking and SOTA for one spec
    {GREEN}forge submit{RESET}                   Validate git and print submission guide
    {GREEN}forge check-deps{RESET}               Verify CalculiX, gmsh, OCP are installed

  {BOLD}Eval options:{RESET}
    --spec ID      Run against one spec (partial match: 001, bracket, ...)
    --round ID     Run against all specs in a competition round
    --all          Run against all specs including round subdirectories
    --json         Output raw JSON

  {BOLD}Environment:{RESET}
    FORGE_API_URL  Override API base (default: {API_BASE})

  {BOLD}Examples:{RESET}
    python cli.py new my-agent
    python cli.py eval agents/my-agent/agent.py --spec 001
    python cli.py eval agents/my-agent/agent.py --round round_001
    python cli.py rounds
    python cli.py status agents/my-agent/agent.py
    python cli.py leaderboard
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
    ingest(n=args.n, out_dir=args.out_dir, seed=args.seed, dry_run=args.dry_run)
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
    p_eval.add_argument("--json", action="store_true", help="Output JSON")
    p_eval.set_defaults(func=cmd_eval)

    p_status = sub.add_parser("status", help="Eval and compare against live SOTA")
    p_status.add_argument("agent", help="Path to agent.py")
    p_status.add_argument("--spec", metavar="ID", help="Limit to one spec")
    p_status.set_defaults(func=cmd_status)

    p_specs = sub.add_parser("specs", help="List available problem specs")
    p_specs.add_argument("--round", metavar="ID", help="Filter to specs in one round (e.g. round_001)")
    p_specs.set_defaults(func=cmd_specs)

    p_rounds = sub.add_parser("rounds", help="List competition rounds and spec sets")
    p_rounds.add_argument("--list-specs", action="store_true", help="Show specs for active round")
    p_rounds.set_defaults(func=cmd_rounds)

    p_lb = sub.add_parser("leaderboard", help="Show current SOTA scores")
    p_lb.add_argument("--spec", metavar="SPEC_ID", help="Per-spec leaderboard for one spec")
    p_lb.add_argument("--history", metavar="SPEC_ID", help="Show SOTA progression for a spec")
    p_lb.set_defaults(func=cmd_leaderboard)

    p_submit = sub.add_parser("submit", help="Validate git setup and print submission guide")
    p_submit.set_defaults(func=cmd_submit)

    p_deps = sub.add_parser("check-deps", help="Verify local dependencies are installed")
    p_deps.set_defaults(func=cmd_check_deps)

    p_ingest = sub.add_parser("ingest", help="Ingest problem specs from Thingiverse")
    p_ingest.add_argument("--n", type=int, default=50, help="Number of specs to generate")
    p_ingest.add_argument("--out-dir", type=Path, default=Path("specs/catalog/"), metavar="DIR")
    p_ingest.add_argument("--seed", type=int, default=0)
    p_ingest.add_argument("--dry-run", action="store_true", help="Preview without writing")
    p_ingest.set_defaults(func=cmd_ingest)

    args = parser.parse_args()
    if not args.command:
        print(HELP_TEXT)
        sys.exit(0)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
