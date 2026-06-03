"""Run forge-eval docker container for each spec in the pool.

Reads SPECS_JSON, AGENT_PATH, and LLM env vars. Runs each spec once.
On the first spec, runs twice to check for non-deterministic output.
Writes results JSON to GITHUB_OUTPUT and exits non-zero if any spec fails.
"""

import json
import os
import subprocess
import sys

# Per-run wall-clock limit. A single docker run should never take more than
# 25 minutes (FEA on complex meshes + LLM latency). The overall job cap is
# 90 minutes; with 4 runs (3 specs + 1 determinism re-run) this gives ~22 min
# per run, leaving headroom for image build and overhead.
DOCKER_RUN_TIMEOUT_SECS = 25 * 60

specs = json.loads(os.environ["SPECS_JSON"])
agent = os.environ["AGENT_PATH"]
llm_key = os.environ.get("FORGE_LLM_KEY", "")
model = os.environ.get("FORGE_MODEL", "anthropic/claude-haiku-4-5")
whitelist = os.environ.get(
    "FORGE_MODEL_WHITELIST",
    "anthropic/claude-haiku-4-5,anthropic/claude-3-5-haiku,openai/gpt-4o-mini",
)
workspace = os.getcwd()

results = []

for idx, spec in enumerate(specs):
    spec_id = spec["spec_id"]
    spec_path = spec["spec_path"]

    ref_flag = []
    if os.path.exists(f"sota/{spec_id}/reference.step"):
        ref_flag = ["--reference-step", f"/forge/sota/{spec_id}/reference.step"]
    elif os.path.exists("sota/reference.step"):
        ref_flag = ["--reference-step", "/forge/sota/reference.step"]

    # Run twice on the first spec to catch non-deterministic agents.
    # All other specs run once — three full determinism checks is too slow.
    runs = 2 if idx == 0 else 1
    prev_score = None
    final_result = None

    for run_i in range(runs):
        step_out_path = f".forge_step_{spec_id}.step"
        step_flag = []
        if run_i == runs - 1:
            # Pre-create the output file world-writable so the container
            # (--cap-drop ALL removes CAP_DAC_OVERRIDE) can write to it.
            with open(step_out_path, "wb"):
                pass
            os.chmod(step_out_path, 0o666)
            step_flag = ["--step-out", f"/forge/{step_out_path}"]

        cmd = [
            "docker", "run", "--rm",
            "--security-opt", "no-new-privileges",
            "--cap-drop", "ALL",
            "--pids-limit", "256",
            "--memory", "4g",
            "--cpus", "2",
            "-e", f"FORGE_LLM_KEY={llm_key}",
            "-e", f"FORGE_MODEL={model}",
            "-e", f"FORGE_MODEL_WHITELIST={whitelist}",
            "-v", f"{workspace}:/forge",
            "forge-eval",
            "--agent", f"/forge/{agent}",
            "--spec", f"/forge/{spec_path}",
            "--json-compact",
        ] + step_flag + ref_flag

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=DOCKER_RUN_TIMEOUT_SECS
            )
        except subprocess.TimeoutExpired:
            # Kill the container that was left running, best-effort.
            subprocess.run(
                ["docker", "ps", "-q", "--filter", f"ancestor=forge-eval"],
                capture_output=True,
                text=True,
            )
            print(
                f"[{spec_id}] run {run_i + 1}/{runs}: TIMEOUT after {DOCKER_RUN_TIMEOUT_SECS}s",
                flush=True,
            )
            result_data = {
                "passed": False,
                "reason": f"Eval timed out after {DOCKER_RUN_TIMEOUT_SECS // 60} minutes",
            }
            final_result = result_data
            break

        out = proc.stdout.strip()
        print(f"[{spec_id}] run {run_i + 1}/{runs}: {out}", flush=True)
        if proc.stderr.strip():
            print(f"[{spec_id}] stderr:\n{proc.stderr.strip()}", flush=True)

        stderr_tail = proc.stderr.strip()[-400:] if proc.stderr.strip() else ""
        if proc.returncode != 0 and not out:
            # Container crashed before producing any output (OOM, segfault, etc.)
            hint = f" | stderr: {stderr_tail}" if stderr_tail else ""
            result_data = {
                "passed": False,
                "reason": f"Container exited {proc.returncode}{hint}",
            }
        else:
            try:
                result_data = json.loads(out)
            except (json.JSONDecodeError, ValueError):
                # Surface the tail of stderr so miners can debug crashes.
                hint = f" | stderr: {stderr_tail}" if stderr_tail else ""
                result_data = {
                    "passed": False,
                    "reason": f"Invalid JSON output: {out[:120]}{hint}",
                }

        # Check determinism on first spec
        if prev_score is not None:
            current_score = result_data.get("score")
            if current_score != prev_score:
                result_data = {
                    "passed": False,
                    "reason": f"Non-deterministic output: run 1={prev_score} run 2={current_score}",
                }
                final_result = result_data
                break

        prev_score = result_data.get("score")
        final_result = result_data

    results.append({**spec, "result": final_result})

results_json = json.dumps(results)

gh_output = os.environ.get("GITHUB_OUTPUT", "")
if gh_output:
    with open(gh_output, "a") as f:
        f.write(f"results={results_json}\n")

failures = [r for r in results if not r["result"].get("passed")]
if failures:
    for r in failures:
        print(
            f"FAIL [{r['spec_id']}]: {r['result'].get('reason', 'unknown')}", flush=True
        )
    sys.exit(1)

print(f"All {len(results)} specs passed.", flush=True)
