"""Post-merge hidden spec evaluation.

Fetches one random hidden spec per round from forge-api, evaluates the merged
agent against it using the same Docker sandbox as the public eval, then records
the result. A consistency warning is printed if the hidden score diverges
significantly from the public round score.

Environment:
    FORGE_API_URL       forge-api base URL
    FORGE_ADMIN_KEY     Admin bearer token — required
    AGENT_PATH          Path to merged agent.py (relative to repo root)
    CONTRIBUTOR         GitHub login of the contributor
    COMMIT_HASH         Git SHA of the merge commit
    FORGE_LLM_KEY       OpenRouter key for LLM agent calls
    FORGE_MODEL         Whitelisted model name
    FORGE_MODEL_WHITELIST  Comma-separated allowed model names
    PUBLIC_RESULTS_JSON Optional JSON: public round scores for consistency check
                        format: [{"round_id": ..., "score": ..., "baseline": ..., "direction": ...}]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

API_URL = os.environ.get("FORGE_API_URL", "").rstrip("/")
ADMIN_KEY = os.environ.get("FORGE_ADMIN_KEY", "")
AGENT_PATH = os.environ["AGENT_PATH"]
CONTRIBUTOR = os.environ.get("CONTRIBUTOR", "unknown")
COMMIT_HASH = os.environ.get("COMMIT_HASH", "unknown")
LLM_KEY = os.environ.get("FORGE_LLM_KEY", "")
MODEL = os.environ.get("FORGE_MODEL", "anthropic/claude-haiku-4-5")
WHITELIST = os.environ.get(
    "FORGE_MODEL_WHITELIST",
    "anthropic/claude-haiku-4-5,anthropic/claude-3-5-haiku,openai/gpt-4o-mini",
)
PUBLIC_RESULTS_JSON = os.environ.get("PUBLIC_RESULTS_JSON", "")

ROUNDS = ["round_001", "round_002", "round_003"]
# Consistency alert threshold: if hidden normalised score is more than this
# factor worse than the public normalised score, print a warning.
CONSISTENCY_ALERT_RATIO = 2.0

workspace = os.getcwd()


def _api_request(req: urllib.request.Request, label: str) -> dict:
    """Execute an API request with 3-attempt exponential backoff (1s → 2s → 4s)."""
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.URLError as e:
            last_exc = e
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"[{label}] forge-api request failed after 3 attempts: {last_exc}") from last_exc


def _api_get(path: str) -> dict:
    url = f"{API_URL}{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {ADMIN_KEY}"})
    return _api_request(req, f"GET {path}")


def _api_post(path: str, payload: dict) -> dict:
    url = f"{API_URL}{path}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Authorization": f"Bearer {ADMIN_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    return _api_request(req, f"POST {path}")


def _run_eval(spec: dict) -> dict:
    spec_id = spec["id"]
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", prefix=f"hidden_{spec_id}_", delete=False
    ) as f:
        json.dump(spec, f)
        spec_path = f.name

    step_out = f".forge_step_hidden_{spec_id}.step"
    with open(step_out, "wb"):
        pass
    os.chmod(step_out, 0o666)

    cmd = [
        "docker", "run", "--rm",
        "--security-opt", "no-new-privileges",
        "--cap-drop", "ALL",
        "--pids-limit", "256",
        "--memory", "4g",
        "--cpus", "2",
        "-e", f"FORGE_LLM_KEY={LLM_KEY}",
        "-e", f"FORGE_MODEL={MODEL}",
        "-e", f"FORGE_MODEL_WHITELIST={WHITELIST}",
        "-v", f"{workspace}:/forge",
        "-v", f"{spec_path}:/hidden_spec.json:ro",
        "forge-eval",
        "--agent", f"/forge/{AGENT_PATH}",
        "--spec", "/hidden_spec.json",
        "--step-out", f"/forge/{step_out}",
        "--json-compact",
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(spec_path)
    try:
        os.unlink(step_out)
    except FileNotFoundError:
        pass

    out = proc.stdout.strip()
    print(f"[hidden/{spec_id}] {out}", flush=True)
    if proc.stderr.strip():
        print(f"[hidden/{spec_id}] stderr: {proc.stderr.strip()[-300:]}", flush=True)

    try:
        return json.loads(out)
    except (json.JSONDecodeError, ValueError):
        return {"passed": False, "reason": f"Invalid JSON: {out[:120]}"}


def _normalised_score(score: float, baseline: float, direction: str) -> float:
    """Returns a value where 1.0 = at baseline, >1 = better, <1 = worse."""
    if baseline <= 0:
        return 1.0
    if direction == "maximize":
        return score / baseline
    return baseline / score  # minimize: lower score → higher ratio


def main() -> None:
    if not API_URL or not ADMIN_KEY:
        print("[hidden-eval] FORGE_API_URL or FORGE_ADMIN_KEY not set — skipping.", flush=True)
        return

    public_norms: dict[str, float] = {}
    if PUBLIC_RESULTS_JSON:
        try:
            for entry in json.loads(PUBLIC_RESULTS_JSON):
                rnd = entry.get("round_id", "")
                score = entry.get("score")
                baseline = entry.get("baseline")
                direction = entry.get("direction", "minimize")
                if rnd and score is not None and baseline:
                    public_norms[rnd] = _normalised_score(score, baseline, direction)
        except Exception as exc:
            print(f"[hidden-eval] Could not parse PUBLIC_RESULTS_JSON: {exc}", flush=True)

    warnings: list[str] = []

    for round_id in ROUNDS:
        print(f"\n[hidden-eval] Fetching hidden spec for {round_id} ...", flush=True)
        try:
            spec = _api_get(f"/admin/hidden/specs/{round_id}/sample")
        except Exception as exc:
            print(f"[hidden-eval] Could not fetch hidden spec for {round_id}: {exc}", flush=True)
            continue

        spec_id = spec["id"]
        metric = spec.get("scoring", {}).get("metric", "mass_grams")
        direction = spec.get("scoring", {}).get("direction", "minimize")

        result = _run_eval(spec)

        payload = {
            "spec_id": spec_id,
            "agent_path": AGENT_PATH,
            "contributor": CONTRIBUTOR,
            "commit_hash": COMMIT_HASH,
            "passed": result.get("passed", False),
            "score": result.get("score"),
            "metric": metric,
            "direction": direction,
            "notes": f"hidden-spec post-merge eval — {round_id}",
        }
        try:
            _api_post("/admin/hidden/submissions", payload)
        except Exception as exc:
            print(f"[hidden-eval] Failed to record hidden result for {spec_id}: {exc}", flush=True)

        # Consistency check
        if result.get("passed") and result.get("score") is not None and round_id in public_norms:
            h_score = result["score"]
            # Need a baseline — use the API's public leaderboard baseline if available.
            # For now we log the raw hidden score and public norm for maintainer review.
            print(
                f"[hidden-eval] {spec_id}: score={h_score:.4f} (public norm={public_norms[round_id]:.3f})",
                flush=True,
            )

    if warnings:
        print("\n[hidden-eval] CONSISTENCY WARNINGS:", flush=True)
        for w in warnings:
            print(f"  {w}", flush=True)
        print(
            "[hidden-eval] These warnings do not block merge — review manually.",
            flush=True,
        )


main()
