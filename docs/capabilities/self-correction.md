# Self-correction

**What it does.** Every draft is checked by a **critic** before the user sees it. The `gate` then
accepts it, asks for a **revision** of the wording, or sends the question back for a **re-plan**
when data is missing. Retries also happen at the tool and model level.

## Layers of self-correction

| Layer | Catches | Mechanism |
|---|---|---|
| Critic + gate | Hallucinated numbers, missing units or timestamps, unanswered parts, hidden failures | `Verdict` → `accept` / `revise` / `replan` |
| Re-plan | Data the plan never fetched | Planner gets `REVIEW FEEDBACK` and fixes the plan |
| Tool retries | Tool errors | `ReflectAndRetryToolPlugin` (reflection prompt + retry) |
| Model retries | Malformed function calls | `ReflectAndRetryModelPlugin` |
| HTTP retries | 429/5xx, transport errors | Executor backoff (2 retries) |
| Model fallback | A provider down or erroring | `FallbackLlm` chain |
| Honest gaps | Unrecoverable failures | Synthesizer rules: say what's unavailable and why; `respond` marks unverified answers |

## The critic's checklist

The critic sets `ok=true` only when all of these hold:

- every part of the question is answered
- every number appears in the step results or tool outputs
- units and data timestamps are stated
- unavailable data is admitted

It sets `missing_data=true` when the plan didn't fetch something the answer needs.

```json title="Verdict"
{"ok": false, "score": 0.55, "issues": ["No units or timestamp on the temperature"], "missing_data": false}
```

## Configuration

| Setting | Default | Effect |
|---|---|---|
| `ACCEPT_SCORE` | 0.75 | Accept at or above this score even when `ok=false` |
| `MAX_REVISIONS` | 2 | Rewrites per turn |
| `MAX_REPLANS` | 1 | Re-plans per turn |
| `CRITIC_MODEL`, `CRITIC_REASONING` | | Use a cheap, strict model; reasoning is optional |
| `MAX_LLM_CALLS_PER_TURN` | 40 | Hard stop for runaway loops |

## Real example: revise

--8<-- "ex_revise.md"

The lesson is in [reflective memory](reflection.md) now. Future planner and synthesizer prompts
for similar questions include it, so the first draft gets it right.

See [Example 6](../examples/replan.md) for a re-plan.
