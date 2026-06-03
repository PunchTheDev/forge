"""Select one easy spec per active round for CI pool evaluation.

Spec selection uses RUN_ID (the GitHub Actions workflow run ID, assigned at
trigger time) XOR-combined with the commit SHA. RUN_ID is not predictable
before a PR is opened, so miners cannot pre-compute which spec they will be
evaluated on and overfit accordingly. PR_NUMBER is kept as a fallback for
local testing only.

Each entry: {round_id, spec_id, spec_path, metric, direction, baseline}.
"""

import hashlib
import json
import os
import pathlib
import sys

# Use run_id (unpredictable at PR-open time) as primary entropy source.
# Fall back to pr_num for local runs where GITHUB_RUN_ID is not set.
run_id = os.environ.get("GITHUB_RUN_ID", "")
commit_sha = os.environ.get("COMMIT_SHA", "")
pr_num = int(os.environ.get("PR_NUMBER", "0"))

if run_id:
    seed_str = f"{run_id}:{commit_sha}"
    seed = int(hashlib.sha256(seed_str.encode()).hexdigest()[:8], 16)
else:
    seed = pr_num

rounds = ["round_001", "round_002", "round_003"]
specs = []

for round_id in rounds:
    d = pathlib.Path(f"specs/{round_id}")
    if not d.exists():
        print(f"WARNING: {d} not found — skipping {round_id}", flush=True)
        continue
    easy = sorted(d.glob("*_easy.json"))
    if not easy:
        print(f"WARNING: no easy specs in {d} — skipping {round_id}", flush=True)
        continue
    chosen = easy[seed % len(easy)]
    data = json.loads(chosen.read_text())
    sc = data.get("scoring", {})
    baseline = (
        sc.get("baseline_mass_grams")
        or sc.get("baseline_stiffness_to_weight")
        or sc.get("baseline_deflection_mm")
        or 1.0
    )
    specs.append(
        {
            "round_id": round_id,
            "spec_id": data["id"],
            "spec_path": str(chosen),
            "metric": sc.get("metric", "mass_grams"),
            "direction": sc.get("direction", "minimize"),
            "baseline": float(baseline),
        }
    )

if not specs:
    print("ERROR: no specs selected — cannot run pool eval", flush=True)
    sys.exit(1)

entropy_source = f"run_id={run_id}" if run_id else f"pr_num={pr_num}"
print(f"Spec selection seed from {entropy_source} → {[s['spec_id'] for s in specs]}", flush=True)

gh_output = os.environ.get("GITHUB_OUTPUT", "")
if gh_output:
    with open(gh_output, "a") as f:
        f.write(f"json={json.dumps(specs)}\n")
        f.write(f"count={len(specs)}\n")
else:
    # Local test: just print
    print(json.dumps(specs, indent=2))
