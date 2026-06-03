"""Post multi-spec CI eval results to the forge-api /submissions endpoint.

Reads EVAL_RESULTS (JSON array from run_eval_pool.py) and records one
submission per spec. Step files named .forge_step_<spec_id>.step are
base64-encoded and included if present.
"""

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

url_base = os.environ.get("FORGE_API_URL", "").strip()
if not url_base:
    print("FORGE_API_URL not set — skipping submission record.")
    sys.exit(0)

results = json.loads(os.environ["EVAL_RESULTS"])
agent_path = os.environ["AGENT_PATH"]
contributor = os.environ["CONTRIBUTOR"]
commit_hash = os.environ["COMMIT_HASH"]
pr_number = int(os.environ.get("PR_NUMBER", "0"))
notes_override = os.environ.get("SCORE_NOTES", "").strip()

url = url_base.rstrip("/") + "/submissions"

for entry in results:
    spec_id = entry["spec_id"]
    result = entry["result"]

    step_b64 = None
    step_file = Path(f".forge_step_{spec_id}.step")
    if step_file.exists():
        step_b64 = base64.b64encode(step_file.read_bytes()).decode()
        step_file.unlink(missing_ok=True)

    score_metric = result.get("score_metric", entry.get("metric", "mass_grams"))
    score_direction = result.get("score_direction", entry.get("direction", "minimize"))
    raw_score = result.get("score") or 0.0
    mass_grams = raw_score if score_metric == "mass_grams" else 0.0

    payload = {
        "spec_id": spec_id,
        "agent_path": agent_path,
        "contributor": contributor,
        "commit_hash": commit_hash,
        "mass_grams": mass_grams,
        "score": raw_score,
        "score_metric": score_metric,
        "score_direction": score_direction,
        "fea_stress_mpa": result.get("fea_stress_mpa") or 0.0,
        "fea_allowable_mpa": result.get("fea_allowable_mpa") or 0.0,
        "passed": bool(result.get("passed", False)),
        "pr_number": pr_number,
        "notes": notes_override or f"CI pool eval — PR #{pr_number}",
        "step_b64": step_b64,
    }

    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"[{spec_id}] recorded: {resp.read().decode()[:80]}")
    except urllib.error.URLError as e:
        print(f"[{spec_id}] forge-api POST failed (non-blocking): {e}", flush=True)
