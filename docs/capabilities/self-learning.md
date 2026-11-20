# Self-learning

**What it does.** The agent learns from its own runs, online, after every answer:

- **new procedures:** successful multi-step runs become reusable composites (Agent Workflow Memory)
- **which procedures and sources to trust:** reliability stats
- **which plans work:** the plan cache
- **what to avoid:** Reflexion lessons
- **which strategies help:** playbook credit and blame (ACE)

The full algorithm is in [LLD: Learning & improvement](../architecture/lld-learning.md).

## The evidence gates

| Learned thing | Requires |
|---|---|
| New composite procedure | Turn accepted **and** ≥ 2 distinct procedures used **and every one of them ran ok** **and** no composite with the same parts exists |
| Promotion (candidate → active) | `success ≥ PROMOTE_AFTER` (default 3) |
| Retirement | ≥ 4 runs and reliability `< DEPRECATE_BELOW` (default 0.35) |
| Plan cache reuse | `successes > failures` and similarity ≥ 0.8 |
| Lesson | The first draft failed review |

The "every one ran ok" rule exists because of a bug the documentation examples caught: an earlier
version learned a composite from a turn where the weather source was down. It's covered by
`test_partial_failure_is_not_learned_as_a_procedure`.

## Real example: four turns

The same multi-part question is asked four times. Everything below comes from running the code.

--8<-- "ex_learning.md"

What happened:

1. **Turn 1:** three procedures worked together and the critic accepted. `learn` induced
   `weather_air_quality_currency_flow` as a **candidate** with `COMPOSED_OF` edges to its parts.
2. **Turns 2–4:** the planner saw the cached plan and the new procedure, and used the composite.
   The compiler expanded it back into its parts and dependencies, still in parallel levels.
3. **Turn 3:** with its third success the procedure was **promoted** to active.

## Configuration

| Setting | Default |
|---|---|
| `LEARNING_ENABLED` | `true` |
| `LEARNER_MODE` | `llm` (`heuristic` needs no model) |
| `LEARNER_MODEL` | any provider spec |
| `PROMOTE_AFTER` | 3 |
| `DEPRECATE_BELOW` | 0.35 |
