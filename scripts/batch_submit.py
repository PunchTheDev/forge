#!/usr/bin/env python3
"""
Batch-submit CI-verified eval results to the forge-api.

Usage:
  # Submit all results from a list of PR numbers:
  ADMIN_SECRET=<token> python3 scripts/batch_submit.py --prs 67,69,73,85,87,96,97,98,99,100,101,102,103,104

  # Submit a single result manually:
  ADMIN_SECRET=<token> python3 scripts/batch_submit.py --manual \
    --spec-id 003_pipe_clamp_bracket \
    --agent agents/ss-bracket-v10/agent.py \
    --contributor Punch \
    --commit bb1317c \
    --mass 88.19 \
    --stress 43.02 \
    --allowable 82.0 \
    --pr 104

Requires:
  - ADMIN_SECRET env var (or --admin-secret flag)
  - gh CLI authenticated (for --prs mode)
  - FORGE_API_URL env var or --api-url flag (default: http://143.244.191.193:8000)

The /admin/submissions/batch endpoint bypasses the per-contributor rate limit.
Requires forge-api PR #8 to be deployed first.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request


def post_batch(api_url: str, admin_secret: str, submissions: list[dict]) -> dict:
    data = json.dumps(submissions).encode()
    req = urllib.request.Request(
        f"{api_url}/admin/submissions/batch",
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-Admin-Token": admin_secret,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"HTTP error {e.code}: {body}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Connection error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def fetch_pr_result(pr_num: int) -> dict | None:
    """Extract eval result and metadata from a GitHub PR's CI run logs."""
    try:
        pr_info = json.loads(subprocess.check_output(
            ["gh", "pr", "view", str(pr_num), "--json",
             "headRefOid,number,statusCheckRollup,headRefName,author"],
            text=True
        ))
    except subprocess.CalledProcessError:
        print(f"  PR #{pr_num}: failed to fetch PR info", file=sys.stderr)
        return None

    checks = pr_info.get("statusCheckRollup", [])
    if not checks:
        print(f"  PR #{pr_num}: no CI runs")
        return None

    check = checks[0]
    if check.get("conclusion") != "SUCCESS":
        print(f"  PR #{pr_num}: CI not successful ({check.get('conclusion')})")
        return None

    details_url = check.get("detailsUrl", "")
    import re
    m = re.search(r"runs/(\d+)/", details_url)
    if not m:
        print(f"  PR #{pr_num}: could not extract run ID from {details_url}")
        return None

    run_id = m.group(1)

    try:
        logs = subprocess.check_output(
            ["gh", "run", "view", run_id, "--log"],
            text=True, stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError:
        print(f"  PR #{pr_num}: failed to fetch logs for run {run_id}")
        return None

    # Extract Run 1 result
    for line in logs.splitlines():
        if "Run 1: " in line and "{" in line:
            json_part = line.split("Run 1: ", 1)[1].strip()
            try:
                result = json.loads(json_part)
                if not result.get("passed"):
                    print(f"  PR #{pr_num}: eval failed ({result.get('reason', '?')})")
                    return None

                # Determine agent path and spec from the branch name
                branch = pr_info.get("headRefName", "")
                agent_name = branch.split("/")[-1]

                # Try to find agent path in logs
                agent_path = None
                for log_line in logs.splitlines():
                    if "AGENT_PATH" in log_line and "agents/" in log_line:
                        parts = log_line.split("agents/")
                        if len(parts) > 1:
                            agent_path = "agents/" + parts[1].strip()
                            break

                if not agent_path:
                    agent_path = f"agents/{agent_name}/agent.py"

                # Determine spec from logs
                spec_id = "001_bracket"
                for log_line in logs.splitlines():
                    if "SPEC_ID:" in log_line or "spec_id=" in log_line:
                        for known in ["001_bracket", "002_equipment_mount", "003_pipe_clamp_bracket"]:
                            if known in log_line:
                                spec_id = known
                                break

                contributor = pr_info.get("author", {}).get("login", "Punch")
                commit_hash = pr_info.get("headRefOid", "")

                return {
                    "spec_id": spec_id,
                    "agent_path": agent_path,
                    "contributor": contributor,
                    "commit_hash": commit_hash,
                    "mass_grams": result["score"],
                    "fea_stress_mpa": result["fea_stress_mpa"],
                    "fea_allowable_mpa": result["fea_allowable_mpa"],
                    "passed": True,
                    "pr_number": pr_num,
                    "notes": f"CI-verified PR #{pr_num}, {result['score']:.2f}g, {result['elapsed_seconds']:.1f}s",
                }
            except (json.JSONDecodeError, KeyError):
                continue

    print(f"  PR #{pr_num}: could not extract eval result from logs")
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch-submit CI results to forge-api")
    parser.add_argument(
        "--api-url",
        default=os.environ.get("FORGE_API_URL", "http://143.244.191.193:8000"),
        help="forge-api base URL",
    )
    parser.add_argument(
        "--admin-secret",
        default=os.environ.get("ADMIN_SECRET", ""),
        help="Admin token for /admin/submissions/batch",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print submissions without posting")

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prs", help="Comma-separated PR numbers to fetch and submit")
    mode.add_argument("--manual", action="store_true", help="Manually specify a single submission")

    # Manual flags
    parser.add_argument("--spec-id")
    parser.add_argument("--agent")
    parser.add_argument("--contributor", default="Punch")
    parser.add_argument("--commit")
    parser.add_argument("--mass", type=float)
    parser.add_argument("--stress", type=float)
    parser.add_argument("--allowable", type=float)
    parser.add_argument("--pr", type=int)
    parser.add_argument("--notes")

    args = parser.parse_args()

    if not args.admin_secret and not args.dry_run:
        print("error: ADMIN_SECRET env var or --admin-secret required", file=sys.stderr)
        return 1

    submissions = []

    if args.prs:
        pr_nums = [int(p.strip()) for p in args.prs.split(",")]
        print(f"Fetching {len(pr_nums)} PRs from GitHub...\n")
        for pr_num in pr_nums:
            print(f"  PR #{pr_num}...", end=" ")
            result = fetch_pr_result(pr_num)
            if result:
                submissions.append(result)
                print(f"OK — {result['mass_grams']:.2f}g {result['spec_id']}")
            else:
                print("skipped")
    else:
        # Manual mode
        if not all([args.spec_id, args.agent, args.commit, args.mass, args.stress, args.allowable]):
            print("error: --manual requires --spec-id, --agent, --commit, --mass, --stress, --allowable")
            return 1
        submissions.append({
            "spec_id": args.spec_id,
            "agent_path": args.agent,
            "contributor": args.contributor,
            "commit_hash": args.commit,
            "mass_grams": args.mass,
            "fea_stress_mpa": args.stress,
            "fea_allowable_mpa": args.allowable,
            "passed": True,
            "pr_number": args.pr,
            "notes": args.notes or f"Manual submission {args.mass:.2f}g",
        })

    if not submissions:
        print("\nNo submissions to post.")
        return 0

    print(f"\n{len(submissions)} submission(s) ready:")
    for s in submissions:
        print(f"  {s['spec_id']:30} {s['mass_grams']:.2f}g  {s['agent_path']}")

    if args.dry_run:
        print("\n[dry-run] Would POST to /admin/submissions/batch")
        print(json.dumps(submissions, indent=2))
        return 0

    print(f"\nPOSTing to {args.api_url}/admin/submissions/batch ...")
    result = post_batch(args.api_url, args.admin_secret, submissions)
    print(f"Inserted: {result.get('inserted', 0)}")
    print(f"Failed:   {result.get('failed', 0)}")
    if result.get("errors"):
        for err in result["errors"]:
            print(f"  Error [{err['index']}]: {err['error']}")
    return 0 if result.get("failed", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
