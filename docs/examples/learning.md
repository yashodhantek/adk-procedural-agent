# 8. Learning a procedure over four turns

The same multi-part question, asked four times.

--8<-- "ex_learning.md"

## What to notice

- **Turn 1:** three procedures (weather, air quality, conversion) succeeded together, so `learn` **induced** a composite and cached the plan.
- **Turns 2–4:** the planner prompt contained the **cached plan**, and the planner used the learned composite. The compiler expanded it back into the same parallel levels.
- **Lifecycle:** the composite went from **candidate** to **active** at its third success (`PROMOTE_AFTER=3`), shown in `learning report` on turn 3.
- **Reliability** rises with each success: (s+1)/(s+f+2).

Related: [Self-learning](../capabilities/self-learning.md) · [LLD: Learning](../architecture/lld-learning.md)
