# Observability & resumability

## What you can see

| Signal | How |
|---|---|
| Every node, tool call and state change | `adk web .` (ADK dev UI) |
| Structured logs | `ADK_LOGGING=1` → ADK `LoggingPlugin` |
| Traces | `ENABLE_TRACING=1` → ADK `AutoTracingPlugin` (OpenTelemetry spans per node, model and tool) |
| What was learned this turn | `last_learning` in session state; `/learned` in `run_cli.py` |
| Graph health | `python scripts/improve.py report`: stats, least reliable procedures and sources, playbook, `.data/kg.mmd` |
| Full turn data | `plan_results.json` artifact per session |
| Ingestion history | `ingest_batches` table and `.data/ingest/<id>.json` |
| Prompt history | `.data/prompts/<role>/vN.md` and `vN.note` (scores) |

## Useful questions to ask the data

```sql
-- Which sources fail most?
SELECT name, success, failure, ROUND(1.0*failure/(success+failure),2) AS fail_rate
FROM sources WHERE success+failure > 0 ORDER BY fail_rate DESC;

-- What has the agent learned, and how is it doing?
SELECT name, status, success, failure FROM procedures WHERE origin='learned';

-- Which playbook bullets are paying off?
SELECT bullet, helpful, harmful FROM playbook WHERE active=1 ORDER BY helpful-harmful DESC;
```

## Resumability

The app sets `ResumabilityConfig(is_resumable=True)`. ADK checkpoints the workflow, so an
interrupted invocation (a crash, a redeploy, a long-running tool) can resume from the last
completed node instead of starting again. Pair it with a persistent session service (SQLite or
Agent Engine).
