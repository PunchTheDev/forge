#!/usr/bin/env python3
"""
forge — local benchmark CLI for miners.

Usage:
  python cli.py eval <agent>            # run benchmark against a single spec
  python cli.py eval <agent> --all      # run against all public specs
  python cli.py eval <agent> --spec 001 # run against a specific spec ID
  python cli.py specs                   # list available problem specs
  python cli.py leaderboard             # show current SOTA scores
  python cli.py check-deps              # verify CalculiX, gmsh, OCP are installed
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
SPECS_DIR = ROOT / "specs"
SOTA_DIR = ROOT / "sota"


def cmd_eval(args: argparse.Namespace) -> int:
    agent_path = Path(args.agent)
    if not agent_path.exists():
        print(f"error: agent not found: {agent_path}", file=sys.stderr)
        return 1

    # Collect specs to run
    if args.all:
        spec_files = sorted(SPECS_DIR.glob("*.json"))
    elif args.spec:
        matches = list(SPECS_DIR.glob(f"*{args.spec}*.json"))
        if not matches:
            print(f"error: no spec matching '{args.spec}'", file=sys.stderr)
            return 1
        spec_files = matches[:1]
    else:
        # Default: run all public specs (same as --all for now)
        spec_files = sorted(SPECS_DIR.glob("*.json"))

    if not spec_files:
        print("error: no specs found in specs/", file=sys.stderr)
        return 1

    overall_pass = True
    results = []

    for spec_file in spec_files:
        spec = json.loads(spec_file.read_text())
        spec_id = spec.get("id", spec_file.stem)

        print(f"\n{'─' * 60}")
        print(f"  spec: {spec_id}  ({spec.get('name', '')})")
        print(f"  agent: {agent_path}")
        print(f"{'─' * 60}")

        result = _run_evaluate(str(agent_path), str(spec_file), verbose=not args.json)

        results.append({"spec": spec_id, **result})

        if not result["passed"]:
            overall_pass = False

    if args.json:
        print(json.dumps(results if len(results) > 1 else results[0], indent=2))
    else:
        if len(results) > 1:
            _print_summary_table(results)

    return 0 if overall_pass else 1


def _run_evaluate(agent_path: str, spec_path: str, verbose: bool) -> dict:
    cmd = [
        sys.executable, "-m", "benchmark.evaluate",
        "--agent", agent_path,
        "--spec", spec_path,
        "--json",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    except FileNotFoundError:
        return {"passed": False, "stage": "error", "reason": "benchmark module not found — run from repo root"}

    # Find JSON in output (evaluate.py may emit non-JSON lines first)
    stdout = proc.stdout.strip()
    result = {}
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
            print(f"  PASSED  score={score:.2f}g  stress={stress}/{allowable} MPa  t={elapsed:.1f}s")
            _compare_sota(result.get("score"), spec_path)
        else:
            stage = result.get("stage", "?")
            reason = result.get("reason", "unknown error")
            print(f"  FAILED  stage={stage}")
            print(f"  reason: {reason}")

    return result


def _compare_sota(score: float | None, spec_path: str) -> None:
    if score is None:
        return
    spec_id = Path(spec_path).stem
    sota_file = SOTA_DIR / "score.json"
    if not sota_file.exists():
        return
    try:
        sota = json.loads(sota_file.read_text())
        sota_score = sota.get("score_grams") or sota.get("mass_grams")
        if sota_score and score < sota_score:
            delta = sota_score - score
            print(f"  🏆  Beats SOTA by {delta:.2f}g ({sota_score:.2f}g → {score:.2f}g)!")
        elif sota_score:
            delta = score - sota_score
            print(f"  SOTA gap: {delta:.2f}g above current best ({sota_score:.2f}g)")
    except (json.JSONDecodeError, KeyError):
        pass


def _print_summary_table(results: list[dict]) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {'SPEC':<20} {'STATUS':<8} {'SCORE':>8}  NOTES")
    print(f"{'─' * 60}")
    for r in results:
        spec = r.get("spec", "?")
        passed = r.get("passed", False)
        status = "PASSED" if passed else "FAILED"
        score = f"{r['score']:.2f}g" if passed and r.get("score") else "—"
        reason = "" if passed else r.get("reason", "")[:30]
        print(f"  {spec:<20} {status:<8} {score:>8}  {reason}")
    print(f"{'─' * 60}\n")


def cmd_specs(args: argparse.Namespace) -> int:
    spec_files = sorted(SPECS_DIR.glob("*.json"))
    if not spec_files:
        print("No specs found in specs/")
        return 0

    print(f"\n  {'ID':<16} {'NAME':<30} {'MATERIAL':<10} {'LOAD'}")
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


def cmd_leaderboard(args: argparse.Namespace) -> int:
    sota_file = SOTA_DIR / "score.json"
    if not sota_file.exists():
        print("No SOTA scores found. Run an eval first.")
        return 0

    try:
        sota = json.loads(sota_file.read_text())
    except json.JSONDecodeError:
        print("error: sota/score.json is malformed", file=sys.stderr)
        return 1

    print("\n  Forge Leaderboard")
    print(f"  {'─' * 60}")
    score = sota.get("score_grams") or sota.get("mass_grams", "?")
    print(f"  SOTA score:    {score} g")
    print(f"  Agent:         {sota.get('agent', '?')}")
    print(f"  FEA stress:    {sota.get('fea_stress_mpa', '?')} / {sota.get('fea_allowable_mpa', '?')} MPa")
    print(f"  Verified:      {sota.get('verified', False)}")
    print(f"  Timestamp:     {sota.get('timestamp', '?')}")
    if sota.get("description"):
        print(f"  Notes:         {sota['description']}")
    print()

    print("  To beat this score, design a lighter bracket that passes FEA.")
    print("  See CONTRIBUTING.md for submission instructions.")
    print()
    return 0


def cmd_check_deps(args: argparse.Namespace) -> int:
    ok = True

    checks = [
        ("python", ["python3", "--version"], None),
        ("ccx (CalculiX)", ["ccx", "-v"], None),
        ("gmsh", ["gmsh", "--version"], None),
    ]

    print("\n  Dependency check")
    print(f"  {'─' * 40}")

    for name, cmd, _ in checks:
        found = shutil.which(cmd[0])
        if found:
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                version = (proc.stdout or proc.stderr).strip().splitlines()[0][:40]
                print(f"  ✓  {name:<22} {version}")
            except Exception:
                print(f"  ✓  {name:<22} (found at {found})")
        else:
            print(f"  ✗  {name:<22} NOT FOUND")
            ok = False

    # Check OCP import
    print(f"  {'─' * 40}")
    try:
        subprocess.run(
            [sys.executable, "-c", "import OCC.Core.BRep; print('ok')"],
            check=True, capture_output=True, timeout=30, cwd=str(ROOT)
        )
        print(f"  ✓  {'OCP (build123d/OCC)':<22} importable")
    except subprocess.CalledProcessError:
        print(f"  ✗  {'OCP (build123d/OCC)':<22} import failed — run: pip install build123d")
        ok = False
    except subprocess.TimeoutExpired:
        print(f"  ?  {'OCP (build123d/OCC)':<22} import timed out (slow cold start is normal)")

    print()
    if ok:
        print("  All dependencies found. You're ready to run evals locally.")
    else:
        print("  Some dependencies are missing. See README.md for install instructions.")
        print("  Alternatively, run evals via Docker: see Dockerfile")
    print()

    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="forge",
        description="Forge benchmark CLI — evaluate agents, browse specs, check SOTA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python cli.py eval agents/baseline/agent.py
  python cli.py eval agents/baseline/agent.py --spec 001
  python cli.py eval agents/baseline/agent.py --all --json
  python cli.py specs
  python cli.py leaderboard
  python cli.py check-deps
        """,
    )
    sub = parser.add_subparsers(dest="command", metavar="command")

    # eval
    p_eval = sub.add_parser("eval", help="Run benchmark against an agent locally")
    p_eval.add_argument("agent", help="Path to agent.py")
    p_eval.add_argument("--spec", metavar="ID", help="Spec ID or partial name (e.g. 001)")
    p_eval.add_argument("--all", action="store_true", help="Run against all available specs")
    p_eval.add_argument("--json", action="store_true", help="Output JSON")
    p_eval.set_defaults(func=cmd_eval)

    # specs
    p_specs = sub.add_parser("specs", help="List available problem specs")
    p_specs.set_defaults(func=cmd_specs)

    # leaderboard
    p_lb = sub.add_parser("leaderboard", help="Show current SOTA scores")
    p_lb.set_defaults(func=cmd_leaderboard)

    # check-deps
    p_deps = sub.add_parser("check-deps", help="Verify local dependencies are installed")
    p_deps.set_defaults(func=cmd_check_deps)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
