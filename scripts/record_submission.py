"""Post a CI eval result to the forge-api /submissions endpoint."""

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

result = json.loads(os.environ["EVAL_RESULT"])

step_b64 = None
step_file = Path(".forge_step_output.step")
if step_file.exists():
    step_b64 = base64.b64encode(step_file.read_bytes()).decode()
    step_file.unlink(missing_ok=True)

score_metric = result.get("score_metric", "mass_grams")
score_direction = result.get("score_direction", "minimize")
raw_score = result.get("score") or 0.0

# mass_grams is always the physical mass; score may be a different metric
# (e.g. stiffness_to_weight). Keep mass_grams as the physical record.
mass_grams = raw_score if score_metric == "mass_grams" else 0.0

payload = {
    "spec_id": os.environ.get("SPEC_ID", "001_bracket"),
    "agent_path": os.environ["AGENT_PATH"],
    "contributor": os.environ["CONTRIBUTOR"],
    "commit_hash": os.environ["COMMIT_HASH"],
    "mass_grams": mass_grams,
    "score": raw_score,
    "score_metric": score_metric,
    "score_direction": score_direction,
    "fea_stress_mpa": result.get("fea_stress_mpa") or 0.0,
    "fea_allowable_mpa": result.get("fea_allowable_mpa") or 0.0,
    "passed": bool(result.get("passed", False)),
    "pr_number": int(os.environ["PR_NUMBER"]),
    "notes": f"CI eval — PR #{os.environ['PR_NUMBER']}",
    "step_b64": step_b64,
}

body = json.dumps(payload).encode()
url = url_base.rstrip("/") + "/submissions"
req = urllib.request.Request(
    url, data=body, headers={"Content-Type": "application/json"}, method="POST"
)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        print(f"Submission recorded: {resp.read().decode()[:120]}")
except urllib.error.URLError as e:
    print(f"forge-api POST failed (non-blocking): {e}", flush=True)
