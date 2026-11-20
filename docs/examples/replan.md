# 6. Critic triggers a re-plan

The question asks for weather **and** air quality, but the plan only fetched weather. The critic sets `missing_data=true`.

--8<-- "ex_replan.md"

## What to notice

- **Re-plan:** the gate routed back to the **planner** (not the synthesizer), because rewriting can't fix missing data. The node path shows the whole pipeline running a second time.
- **Bounded:** `MAX_REPLANS=1`, so a second missing-data verdict would fall through to a revision, then to an answer marked unverified.
- In this recorded run the scripted planner returned the same plan both times, so the levels match. A real planner adds the `get_air_quality` step after reading the feedback.

Related: [Self-correction](../capabilities/self-correction.md) · [LLD: routing policy](../architecture/lld-workflow.md#routing-policy-gate)
