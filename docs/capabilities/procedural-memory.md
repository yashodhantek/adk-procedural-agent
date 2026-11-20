# Procedural memory & skills

**What it does.** Stores *how to do things* as a graph of procedures that the agent can search,
compose, execute, measure and extend. It's the agent's long-term know-how. Design details are in
[LLD: Procedural knowledge graph](../architecture/lld-procedural-graph.md).

## A procedure

| Field | Example (`get_fx_rate`) |
|---|---|
| name, domain, description | `get_fx_rate`, finance, "Latest exchange rate between two currencies…" |
| inputs → outputs | `from_currency, to_currency` → `rate, date` |
| steps (markdown) | "1. Normalise currency names to ISO-4217 codes. 2. Call Frankfurter /latest. 3. Note the rate date…" |
| call spec | `http_json` to `api.frankfurter.app/latest`, extract `rates.{to_currency}` |
| status, origin, version | `active`, `seed`, 1 |
| stats | success, failure, total latency → reliability |

Procedures can be:

- **executable**: they have a call spec, and the [executor](../architecture/lld-executor.md) runs them
- **written-steps only**: they have no call spec, and the synthesizer follows them as an ADK Skill with its tools

## Four ways the graph grows

| Source | Origin | Starts as | How |
|---|---|---|---|
| Seed file | `seed` | active | `seed/procedures.json` on first start |
| Documents | `ingested` | candidate | [Ingestion](ingestion.md) with review |
| The user teaches it | `user` | active | `teach_procedure` tool in chat |
| The agent learns it | `learned` | candidate | [Self-learning](self-learning.md) induction |

## Procedures as ADK Skills

The synthesizer sees the graph through ADK's `SkillToolset` and a custom `KGSkillRegistry`:

```text
search_skills("air quality")      → get-air-quality (environment, reliability 0.93, active), city-conditions-brief, …
load_skill("get-air-quality")     → steps, inputs/outputs, depends on geocode_city, version, origin
load_skill_resource("…", "call_spec.json" | "lessons.md")
```

This is ADK's progressive disclosure: the model loads detail only for the procedures it needs.

## Plan cache

A successful plan is cached under its question's token signature. The next similar question
(Jaccard ≥ 0.8) brings the plan back to the planner as `CACHED PLAN`, along with its success count.
[Example 8](../examples/learning.md) shows the cache being used on turns 2–4.

## Reliability

Every execution records an outcome. `reliability = (success+1)/(success+failure+2)` feeds search
ranking, the planner's candidate list, promotion and retirement, and `improve.py report`. Data
sources are measured the same way ([Example 7](../examples/failure.md)).

## The graph after the documentation examples ran

This is the real graph produced by running all the examples: seed procedures, learned composites
(double borders) and ingested ones.

--8<-- "graph_after.md"

--8<-- "kg_stats.md"
