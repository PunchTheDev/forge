## Summary

<!-- What does your agent do? What approach did you use? -->

## Spec

<!-- Which spec does this target? (e.g., 001_bracket) -->

## Score

<!-- CI will post your score automatically. Paste it here once CI runs. -->

## Approach

<!-- Brief technical description: topology optimization? parametric? lattice? -->

## Checklist

- [ ] `agents/<my-name>/agent.py` implements `generate(spec) -> bytes`
- [ ] Local eval passes: `docker run ... --agent agents/<my-name>/agent.py --spec specs/001_bracket.json`
- [ ] No external network calls in `generate()`
- [ ] Agent is deterministic (same output for same spec)
