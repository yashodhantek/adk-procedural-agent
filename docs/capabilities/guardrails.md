# Guardrails & safety

| Risk | Guardrail | Where |
|---|---|---|
| Calling arbitrary hosts (SSRF, data exfiltration) | `HTTP_ALLOWLIST` on every procedure call and `http_get_json` | `executor.HttpFetcher.check` |
| Code execution through formulas | AST-whitelist evaluator (numbers, variables, arithmetic, `round/min/max/abs/float`) | `executor.safe_eval` |
| Runaway loops and cost | Bounded revise/replan counters; `BudgetGuardPlugin` per-turn model-call cap | `nodes.gate`, `plugins.py` |
| Hallucinated numbers | Critic rule: every number must appear in the results; grounding rules in the synthesizer prompt | `prompts/` |
| Hidden failures | Failed and skipped steps are passed to the synthesizer and critic; the critic requires gaps to be admitted | `nodes`, `prompts/critic.md` |
| Unreviewed knowledge | Ingestion is staged; I/O-inferred edges need approval; new procedures start as candidates | `ingest.py` |
| Bad learned procedures | Evidence gates; promotion threshold; automatic retirement; consolidation | `nodes.learn`, `improve.py` |
| Graph corruption | Cycle checks on every edge and at compile time | `procedural_kg.py` |
| Tool-call tampering | Optional HMAC integrity (`TOOL_CALL_HMAC_KEY`) | ADK `ToolCallIntegrityPlugin` |
| Secrets in memory | Credentials come from the environment and are never stored in the graph; `describe()` masks keys | `llm.py` |
| Prompt regressions | Optimised prompts are activated only when they beat the baseline; one-command rollback | `improve.py`, `prompts/__init__.py` |
| Remembering inferences | `remember_fact` is for facts the user **stated**; `forget_fact` on request | prompt + tools |

## Recommended production settings

```bash
HTTP_ALLOWLIST=api.yourcompany.com,api.open-meteo.com,...   # never "*"
MAX_LLM_CALLS_PER_TURN=25
TOOL_CALL_HMAC_KEY=<random 32+ bytes>
ENABLE_TRACING=1
```

Write actions, such as creating tickets or sending messages through MCP, should require explicit
user confirmation. That's a planned procedure flag (`side_effect: write`); see the
[Roadmap](../roadmap.md).
