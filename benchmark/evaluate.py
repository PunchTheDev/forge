"""
Main evaluation entry point.

Usage:
  python -m benchmark.evaluate --agent agents/baseline/agent.py --spec specs/001_bracket.json

Exit codes:
  0 = passed with score
  1 = failed (geometry/FEA/similarity)
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

# Submissions scoring ≥ this similarity to the current SOTA reference are rejected.
SIMILARITY_THRESHOLD = 0.95

# Supported scoring metrics and their optimization direction.
# "minimize" = lower score is better; "maximize" = higher score is better.
METRICS: dict[str, str] = {
    "mass_grams": "minimize",
    "volume_mm3": "minimize",
    "stiffness_to_weight": "maximize",  # N/(mm·g) — stiffer and lighter wins
}


@dataclass
class EvalResult:
    passed: bool
    score: float | None  # objective metric value; None if failed
    score_metric: str    # which metric was scored (matches spec["scoring"]["metric"])
    score_direction: str # "minimize" or "maximize"
    stage: str           # "agent" | "geometry" | "fea" | "similarity" | "ok"
    reason: str
    fea_stress_mpa: float | None = None
    fea_allowable_mpa: float | None = None
    fea_element_count: int | None = None
    fea_load_node_count: int | None = None
    fea_convergence_deviation: float | None = None
    fea_displacement_mm: float | None = None  # max Z-displacement from FEA (mm)
    similarity: float | None = None
    elapsed_seconds: float = 0.0
    step_bytes: bytes | None = None


def _compute_score(
    geo: geometry.GeometryResult,
    fea_result: fea.FEAResult,
    spec: dict,
    metric: str,
) -> float:
    """Compute the objective score for a passed evaluation."""
    if metric == "volume_mm3":
        return geo.volume_mm3
    if metric == "stiffness_to_weight":
        disp = fea_result.max_displacement_mm
        if disp is None or disp <= 0:
            raise ValueError(
                "stiffness_to_weight requires displacement output from FEA. "
                "Displacement was zero or not parsed — check FEA .frd output."
            )
        load_n = spec["constraints"]["load_newtons"]
        stiffness = load_n / disp  # N/mm
        return stiffness / geo.mass_grams  # N/(mm·g)
    # Default: mass_grams
    return geo.mass_grams


def evaluate(agent_path: str, spec_path: str, reference_step_path: str | None = None) -> EvalResult:
    spec = json.loads(Path(spec_path).read_text())
    mat = materials.get(spec["material"])

    scoring = spec.get("scoring", {})
    metric = scoring.get("metric", "mass_grams")
    if metric not in METRICS:
        raise ValueError(f"Unsupported scoring metric '{metric}'. Supported: {sorted(METRICS)}")
    direction = METRICS[metric]

    # Stage 1: Run agent in sandbox
    agent_result = run_agent(agent_path, spec)
    if not agent_result.success:
        return EvalResult(
            passed=False,
            score=None,
            score_metric=metric,
            score_direction=direction,
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
            score_metric=metric,
            score_direction=direction,
            stage="geometry",
            reason=geo.reason,
            elapsed_seconds=agent_result.elapsed_seconds,
        )

    # Stage 3: FEA stress check (correctness gate).
    # For near-limit designs, a second pass at finer mesh checks convergence.
    fea_result = fea.run(step_bytes, spec, mat)
    if not fea_result.passed:
        return EvalResult(
            passed=False,
            score=None,
            score_metric=metric,
            score_direction=direction,
            stage="fea",
            reason=fea_result.reason,
            fea_stress_mpa=fea_result.max_stress_mpa,
            fea_allowable_mpa=fea_result.allowable_mpa,
            fea_element_count=fea_result.element_count or None,
            fea_load_node_count=fea_result.load_node_count or None,
            fea_convergence_deviation=fea_result.convergence_deviation,
            fea_displacement_mm=fea_result.max_displacement_mm,
            elapsed_seconds=agent_result.elapsed_seconds,
        )

    # Stage 4: Geometric similarity check (anti-copying gate).
    similarity_score: float | None = None
    if reference_step_path is not None:
        ref_path = Path(reference_step_path)
        if ref_path.exists():
            try:
                from benchmark.similarity import compute
                similarity_score = compute(step_bytes, ref_path.read_bytes())
                if similarity_score >= SIMILARITY_THRESHOLD:
                    return EvalResult(
                        passed=False,
                        score=None,
                        score_metric=metric,
                        score_direction=direction,
                        stage="similarity",
                        reason=(
                            f"Submission is {similarity_score:.1%} geometrically similar to the "
                            f"current SOTA reference (threshold {SIMILARITY_THRESHOLD:.0%}). "
                            "Substantially differentiate your design."
                        ),
                        fea_stress_mpa=fea_result.max_stress_mpa,
                        fea_allowable_mpa=fea_result.allowable_mpa,
                        fea_element_count=fea_result.element_count or None,
                        fea_load_node_count=fea_result.load_node_count or None,
                        fea_displacement_mm=fea_result.max_displacement_mm,
                        similarity=similarity_score,
                        elapsed_seconds=agent_result.elapsed_seconds,
                    )
            except Exception as exc:
                # Non-fatal: log and continue. A broken similarity check should not
                # block a legitimate submission.
                print(f"[similarity] check failed (skipped): {exc}", file=sys.stderr)

    # Compute objective score
    try:
        score = _compute_score(geo, fea_result, spec, metric)
    except ValueError as exc:
        return EvalResult(
            passed=False,
            score=None,
            score_metric=metric,
            score_direction=direction,
            stage="fea",
            reason=str(exc),
            fea_stress_mpa=fea_result.max_stress_mpa,
            fea_allowable_mpa=fea_result.allowable_mpa,
            fea_element_count=fea_result.element_count or None,
            fea_load_node_count=fea_result.load_node_count or None,
            fea_displacement_mm=fea_result.max_displacement_mm,
            elapsed_seconds=agent_result.elapsed_seconds,
        )

    return EvalResult(
        passed=True,
        score=score,
        score_metric=metric,
        score_direction=direction,
        stage="ok",
        reason="",
        fea_stress_mpa=fea_result.max_stress_mpa,
        fea_allowable_mpa=fea_result.allowable_mpa,
        fea_element_count=fea_result.element_count or None,
        fea_load_node_count=fea_result.load_node_count or None,
        fea_convergence_deviation=fea_result.convergence_deviation,
        fea_displacement_mm=fea_result.max_displacement_mm,
        similarity=similarity_score,
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
    parser.add_argument(
        "--reference-step",
        metavar="PATH",
        default=None,
        help="Path to current SOTA reference STEP for similarity check (optional)",
    )
    args = parser.parse_args()

    result = evaluate(args.agent, args.spec, reference_step_path=args.reference_step)

    if args.step_out and result.step_bytes is not None:
        Path(args.step_out).write_bytes(result.step_bytes)

    payload = {
        "passed": result.passed,
        "score": result.score,
        "score_metric": result.score_metric,
        "score_direction": result.score_direction,
        "stage": result.stage,
        "reason": result.reason,
        "fea_stress_mpa": result.fea_stress_mpa,
        "fea_allowable_mpa": result.fea_allowable_mpa,
        "fea_element_count": result.fea_element_count,
        "fea_load_node_count": result.fea_load_node_count,
        "fea_convergence_deviation": result.fea_convergence_deviation,
        "fea_displacement_mm": result.fea_displacement_mm,
        "similarity": result.similarity,
        "elapsed_seconds": result.elapsed_seconds,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    elif args.json_compact:
        print(json.dumps(payload, separators=(",", ":")))
    else:
        if result.passed:
            sim_str = f"  similarity={result.similarity:.2f}" if result.similarity is not None else ""
            disp_str = f"  disp={result.fea_displacement_mm:.4f}mm" if result.fea_displacement_mm else ""
            print(
                f"PASSED  {result.score_metric}={result.score:.4g}  "
                f"stress={result.fea_stress_mpa:.1f}/{result.fea_allowable_mpa:.1f} MPa  "
                f"t={result.elapsed_seconds:.1f}s{disp_str}{sim_str}"
            )
        else:
            print(f"FAILED  stage={result.stage}  reason={result.reason}")

    sys.exit(0 if result.passed else (2 if result.stage == "agent" else 1))


if __name__ == "__main__":
    main()
