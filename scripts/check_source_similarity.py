#!/usr/bin/env python3
"""
CI pre-eval script: check agent source similarity against known reference agents.

Exits 0 if the agent is sufficiently different from all references.
Exits 1 if the agent is too similar (likely a copy), printing the offending
comparison so the CI comment surfaces the reason.

Usage:
    python3 scripts/check_source_similarity.py --agent agents/alice/agent.py

References checked (in order):
  1. agents/baseline/agent.py — the reference implementation every miner sees
  2. Any other agent.py files merged on the base branch (catches cross-miner copies)

Thresholds:
  >= 0.95  — rejected (too similar)
  0.80–0.95 — warning logged but not blocked (manual review recommended)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from benchmark.agent_similarity import compare

REJECT_THRESHOLD = 0.95
WARN_THRESHOLD = 0.80


def _find_reference_agents(exclude: Path) -> list[Path]:
    """Return all agent.py files in agents/ except the one being checked and the template."""
    agents_dir = ROOT / "agents"
    refs: list[Path] = []
    for p in agents_dir.rglob("agent.py"):
        if p.resolve() == exclude.resolve():
            continue
        if "template" in p.parts:
            continue
        refs.append(p)
    return refs


def main() -> int:
    parser = argparse.ArgumentParser(description="Check agent source similarity")
    parser.add_argument("--agent", required=True, help="Path to the agent.py being evaluated")
    args = parser.parse_args()

    agent_path = Path(args.agent)
    if not agent_path.exists():
        print(f"error: agent file not found: {agent_path}", file=sys.stderr)
        return 1

    candidate = agent_path.read_text(encoding="utf-8", errors="replace")
    refs = _find_reference_agents(agent_path)

    if not refs:
        print("No reference agents found — skipping similarity check.")
        return 0

    rejected = False
    warned = False

    for ref_path in refs:
        ref_source = ref_path.read_text(encoding="utf-8", errors="replace")
        score = compare(candidate, ref_source)

        rel = ref_path.relative_to(ROOT)
        if score >= REJECT_THRESHOLD:
            print(
                f"SIMILARITY REJECT: {agent_path.relative_to(ROOT)} vs {rel} "
                f"— score {score:.3f} >= {REJECT_THRESHOLD} threshold"
            )
            print(
                "The submitted agent is too similar to an existing reference implementation. "
                "This looks like a verbatim copy or trivial rename. "
                "Submissions must represent an original optimization approach."
            )
            rejected = True
        elif score >= WARN_THRESHOLD:
            print(
                f"SIMILARITY WARNING: {agent_path.relative_to(ROOT)} vs {rel} "
                f"— score {score:.3f} (threshold: {REJECT_THRESHOLD}). "
                "Manual review recommended."
            )
            warned = True
        else:
            print(
                f"SIMILARITY OK: {agent_path.relative_to(ROOT)} vs {rel} "
                f"— score {score:.3f}"
            )

    return 1 if rejected else 0


if __name__ == "__main__":
    sys.exit(main())
