## Summary

<!-- What does your agent do? What approach did you use? -->

## Score

<!-- CI will post your cross-category score automatically. Paste it here once CI runs. -->

## Approach

<!-- Brief technical description: topology optimization? parametric? LLM-guided? lattice? -->

## Checklist

- [ ] `agents/<my-name>/agent.py` implements `generate(spec, llm) -> bytes`
- [ ] Agent handles all three metric types: `mass_grams`, `stiffness_to_weight`, `deflection_mm`
- [ ] Local eval passes on at least one spec from each round
- [ ] Agent is deterministic (same spec + seed → same bytes)
- [ ] LLM agents: using the injected `LLMClient`, not a hardcoded API key
