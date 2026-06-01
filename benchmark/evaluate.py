"""
Main evaluation entry point.

Usage:
  python -m benchmark.evaluate --agent agents/baseline/agent.py --spec specs/001_bracket.json

Exit codes:
  0 = passed with score
  1 = failed (geometry/FEA)
  2 = agent error
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from benchmark import geometry, fea, materials
from benchmark.sandbox import preload_ocp, run_agent

# Pre-load OCP modules before any subprocess is forked.
# On Linux (fork-based multiprocessing) this makes OCP import free in workers.
preload_ocp()


@dataclass
class EvalResult:
    passed: bool
    score: float | None  # mass in grams; None if failed
    stage: str  # "agent" | "geometry" | "fea" | "ok"
    reason: str
    fea_stress_mpa: float | None = None
    fea_allowable_mpa: float | None = None
    elapsed_seconds: float = 0.0
    step_bytes: bytes | None = None  # raw STEP output; populated only on pass


def evaluate(agent_path: str, spec_path: str) -> EvalResult:
    spec = json.loads(Path(spec_path).read_text())
    mat = materials.get(spec["material"])

    # Stage 1: Run agent in sandbox
    agent_result = run_agent(agent_path, spec)
    if not agent_result.success:
        return EvalResult(
            passed=False,
            score=None,
            stage="agent",
            reason=agent_result.error,
            elapsed_seconds=agent_result.elapsed_seconds,
        )

    step_bytes = agent_result.step_bytes

    # Stage 2: Geometry validation (volume, bolt holes, overhang, build volume)
    geo = geometry.validate(step_bytes, spec, mat)
    if not geo.passed:
        return EvalResult(
            passed=False,
            score=None,
            stage="geometry",
            reason=geo.reason,
            elapsed_seconds=agent_result.elapsed_seconds,
        )

    # Stage 3: FEA stress check (correctness gate)
    fea_result = fea.run(step_bytes, spec, mat)
    if not fea_result.passed:
        return EvalResult(
            passed=False,
            score=None,
            stage="fea",
            reason=fea_result.reason,
            fea_stress_mpa=fea_result.max_stress_mpa,
            fea_allowable_mpa=fea_result.allowable_mpa,
            elapsed_seconds=agent_result.elapsed_seconds,
        )

    return EvalResult(
        passed=True,
        score=geo.mass_grams,
        stage="ok",
        reason="",
        fea_stress_mpa=fea_result.max_stress_mpa,
        fea_allowable_mpa=fea_result.allowable_mpa,
        elapsed_seconds=agent_result.elapsed_seconds,
        step_bytes=step_bytes,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Forge benchmark evaluator")
    parser.add_argument("--agent", required=True, help="Path to agent.py")
    parser.add_argument("--spec", required=True, help="Path to spec JSON")
    parser.add_argument("--json", action="store_true", help="Output pretty JSON")
    parser.add_argument("--json-compact", action="store_true", help="Output single-line JSON (safe for shell capture)")
    parser.add_argument("--step-out", metavar="PATH", help="Write STEP bytes to this path on pass")
    args = parser.parse_args()

    result = evaluate(args.agent, args.spec)

    if args.step_out and result.step_bytes is not None:
        Path(args.step_out).write_bytes(result.step_bytes)

    payload = {
        "passed": result.passed,
        "score": result.score,
        "stage": result.stage,
        "reason": result.reason,
        "fea_stress_mpa": result.fea_stress_mpa,
        "fea_allowable_mpa": result.fea_allowable_mpa,
        "elapsed_seconds": result.elapsed_seconds,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    elif args.json_compact:
        print(json.dumps(payload, separators=(",", ":")))
    else:
        if result.passed:
            print(f"PASSED  score={result.score:.2f} g  stress={result.fea_stress_mpa:.1f}/{result.fea_allowable_mpa:.1f} MPa  t={result.elapsed_seconds:.1f}s")
        else:
            print(f"FAILED  stage={result.stage}  reason={result.reason}")

    sys.exit(0 if result.passed else (2 if result.stage == "agent" else 1))


if __name__ == "__main__":
    main()
