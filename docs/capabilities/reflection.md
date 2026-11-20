# Reflection & playbook

Two kinds of learned guidance reach every prompt through the dynamic instruction:

| | Reflective lessons (Reflexion) | Playbook (ACE-style evolving context) |
|---|---|---|
| **Granularity** | One concrete lesson per mistake | Short, general strategy bullets |
| **Written when** | The first draft didn't pass review | Seeded; the curator adds bullets after imperfect turns |
| **Retrieved** | Only lessons relevant to the question (FTS5 / Jaccard) | Top `PLAYBOOK_SIZE` by `helpful − harmful` |
| **Feedback** | `uses` counter; forgotten if never used for 60 days | `helpful`/`harmful` counters; pruned at a net score of −2 |
| **Also used in** | Skill resource `lessons.md` | — |

## Lessons

Written by `learn` when the turn needed a revision or a re-plan:

```json
{"id": 1, "scope": "global",
 "lesson": "For questions like 'How hot is it in Delhi?': No units or timestamp on the temperature"}
```

That's the heuristic distiller's wording. With `LEARNER_MODE=llm`, the learner model writes a
generalised, actionable sentence, such as *"Always give the unit and the observation time for
temperatures."* Near-duplicates aren't stored twice.

They show up for similar questions under `Lessons from past mistakes:` in the planner and
synthesizer prompts.

## Playbook

Seed bullets:

```text
- [strategy#1] Prefer executable procedures from the graph over ad-hoc web calls; they are faster and validated.
- [strategy#2] Run independent data fetches in the same plan level so they execute in parallel.
- [pitfall#3] Always state the timestamp or date of real-time data; never present stale values as current.
- [formatting#4] Lead with the direct answer, then the supporting numbers with units.
```

Credit assignment after each turn:

- every bullet that was in context gets **helpful +1** on a first-try success, or **harmful +1** otherwise
- on imperfect turns, the curator proposes up to 2 new bullets that would have prevented the issues
- `improve.py consolidate` deactivates bullets whose `helpful − harmful ≤ −2`

## Real example

--8<-- "ex_revise.md"
