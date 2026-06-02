## Summary

<!-- What does your agent do? What approach did you use? -->

## Spec

<!-- Which spec does this target? (e.g., pub_001_medium) -->

## Score

<!-- CI will post your score automatically. Paste it here once CI runs. -->

## Approach

<!-- Brief technical description: topology optimization? parametric? LLM-guided? lattice? -->

## Checklist

- [ ] `agents/<my-name>/agent.py` implements `generate(spec) -> bytes` or `generate(spec, llm) -> bytes`
- [ ] `agents/<my-name>/spec.txt` contains the target spec ID (e.g., `pub_001_medium`)
- [ ] Local eval passes: `forge eval agents/<my-name>/agent.py`
- [ ] Agent is deterministic (same spec → same bytes; fix any random seeds)
- [ ] LLM agents: using an injected `LLMClient`, not a hardcoded API key
