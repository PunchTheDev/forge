"""Select one easy spec per active round for CI pool evaluation.

Reads PR_NUMBER from env, outputs a JSON list to GITHUB_OUTPUT.
Each entry: {round_id, spec_id, spec_path, metric, direction, baseline}.
Specs are chosen deterministically: index = PR_NUMBER % len(easy_specs).
This means different PRs test different specs, making it hard to overfit
to a single problem while keeping evaluation reproducible per PR.
"""

import json
import os
import pathlib
import sys

pr_num = int(os.environ.get("PR_NUMBER", "0"))
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
    chosen = easy[pr_num % len(easy)]
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

print(f"Selected {len(specs)} specs: {[s['spec_id'] for s in specs]}", flush=True)

gh_output = os.environ.get("GITHUB_OUTPUT", "")
if gh_output:
    with open(gh_output, "a") as f:
        f.write(f"json={json.dumps(specs)}\n")
        f.write(f"count={len(specs)}\n")
else:
    # Local test: just print
    print(json.dumps(specs, indent=2))
