# Request lifecycle

One question, end to end. The path is the same every time; only the loops (revise or re-plan) and
the learning outcomes vary.

```mermaid
sequenceDiagram
  autonumber
  actor U as User
  participant W as Workflow
  participant M as Memory stores
  participant P as Planner (LLM)
  participant K as Procedural KG
  participant X as Executor
  participant A as Data APIs
  participant S as Synthesizer (LLM + tools)
  participant C as Critic (LLM)
  participant L as Learner

  U->>W: question
  W->>M: recall: episodes, facts, glossary terms,<br/>candidate procedures, cached plan, lessons, playbook
  W->>P: question + everything recalled
  P-->>W: Plan (steps, inputs, depends_on)
  W->>K: normalise inputs (glossary) + compile
  K-->>W: levels (closure added, composites expanded)
  loop each level, steps in parallel
    W->>X: run step
    X->>A: HTTP / compute / composite
    A-->>X: data
    X->>K: record procedure + source outcome
  end
  W->>S: question + plan + step results
  S->>S: optional tools: skills, run_procedure,<br/>search, memory, MCP
  S-->>W: draft
  W->>C: question + results + draft
  C-->>W: Verdict (ok, score, issues, missing_data)
  alt accept
    W-->>U: answer
    W->>L: learn
    L->>K: plan cache · induce / promote / retire procedures
    L->>M: Reflexion lesson · playbook scores and new bullets
  else revise (≤ MAX_REVISIONS)
    W->>S: previous draft + issues
  else replan (missing data, ≤ MAX_REPLANS)
    W->>P: question + feedback
  end
  Note over W,M: After the run: EpisodicMemoryPlugin writes the session to long-term memory
```

## What each stage adds

| # | Stage | Adds to state | Typical cost |
|---|---|---|---|
| 1 | `recall` | `temp:brief`, `temp:playbook`, `temp:lessons`, `temp:query` | Milliseconds (SQLite + memory search) |
| 2 | `planner` | `plan` | 1 LLM call (structured output) |
| 3 | `compile_plan` | `temp:compiled` (levels, added steps, normalisations) | Milliseconds |
| 4 | `execute_plan` | `temp:results`, artifact `plan_results.json` | Slowest level × number of levels |
| 5 | `synthesizer` | `draft` | 1+ LLM calls (more if it uses tools) |
| 6 | `critic` | `verdict`, `temp:verdicts` | 1 LLM call |
| 7 | `gate` | route `accept` / `revise` / `replan` | — |
| 8 | `respond` | final message | — |
| 9 | `learn` | `last_learning` | 0–3 LLM calls (only when something is learned) |

See it with real values in the [worked examples](../examples/index.md). The
[Example 6 node path](../examples/replan.md) shows a full re-plan loop.
