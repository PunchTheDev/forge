#!/usr/bin/env bash
# Update sota/reference.step after merging a new SOTA agent.
#
# Run this from the repo root after merging a PR that beats the current SOTA.
# Requires Docker.
#
# Usage:
#   ./scripts/update_sota_reference.sh agents/my-agent/agent.py
#
# The script runs the agent inside the eval container and writes its STEP
# output to sota/reference.step, which CI uses for the similarity check.

set -euo pipefail

AGENT="${1:-}"
SPEC="${2:-specs/001_bracket.json}"

if [ -z "$AGENT" ]; then
  echo "Usage: $0 <agent_path> [spec_path]"
  echo "Example: $0 agents/slim-spine/agent.py"
  exit 1
fi

if [ ! -f "$AGENT" ]; then
  echo "Agent not found: $AGENT"
  exit 1
fi

echo "Building eval image..."
docker build -t forge-eval . -q

echo "Running agent to generate reference STEP..."
docker run --rm \
  --network none \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --memory 4g \
  --cpus 2 \
  -v "$(pwd):/forge" \
  forge-eval \
  --agent "/forge/$AGENT" \
  --spec "/forge/$SPEC" \
  --step-out /forge/sota/reference.step \
  --json-compact 2>/dev/null

if [ -f "sota/reference.step" ]; then
  echo "Done. sota/reference.step updated."
  echo "Commit it: git add sota/reference.step && git commit -m 'Update SOTA reference STEP'"
else
  echo "ERROR: agent failed or produced no STEP output."
  exit 1
fi
