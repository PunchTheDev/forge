"""Select all specs in a round for post-merge comprehensive scoring.

Reads ROUND_ID from env, loads the round config, outputs all spec entries
as a JSON list to GITHUB_OUTPUT. Each entry matches the format expected by
run_eval_pool.py: {round_id, spec_id, spec_path, metric, direction, baseline}.
"""

import json
import os
import pathlib
import sys

round_id = os.environ.get("ROUND_ID", "").strip()
if not round_id:
    print("ERROR: ROUND_ID not set", flush=True)
    sys.exit(1)

round_file = pathlib.Path(f"rounds/{round_id}.json")
if not round_file.exists():
    print(f"ERROR: round config not found: {round_file}", flush=True)
    sys.exit(1)

round_cfg = json.loads(round_file.read_text())

if round_cfg.get("status") != "active":
    print(f"Round {round_id} is not active — skipping.", flush=True)
    # Exit 0 so the workflow job succeeds but does no work.
    gh_output = os.environ.get("GITHUB_OUTPUT", "")
    if gh_output:
        with open(gh_output, "a") as f:
            f.write("json=[]\n")
            f.write("count=0\n")
    sys.exit(0)

metric = round_cfg.get("scoring_metric", "mass_grams")
direction = round_cfg.get("scoring_direction", "minimize")

specs = []
for entry in round_cfg.get("specs", []):
    spec_path = pathlib.Path(entry["file"])
    if not spec_path.exists():
        print(f"WARNING: spec file missing: {spec_path} — skipping", flush=True)
        continue
    data = json.loads(spec_path.read_text())
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
            "spec_path": str(spec_path),
            "metric": sc.get("metric", metric),
            "direction": sc.get("direction", direction),
            "baseline": float(baseline),
        }
    )

if not specs:
    print(f"ERROR: no specs found for round {round_id}", flush=True)
    sys.exit(1)

print(
    f"Round {round_id}: {len(specs)} specs — "
    f"{[s['spec_id'] for s in specs]}",
    flush=True,
)

gh_output = os.environ.get("GITHUB_OUTPUT", "")
if gh_output:
    with open(gh_output, "a") as f:
        f.write(f"json={json.dumps(specs)}\n")
        f.write(f"count={len(specs)}\n")
else:
    print(json.dumps(specs, indent=2))
