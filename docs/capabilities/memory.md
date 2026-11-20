# Memory: working, session, user, episodic, semantic, artifacts

The agent uses eleven kinds of memory. This page covers the six that hold **conversation and user
context**. Procedural memory, the glossary, reflection and the playbook each have their own page.
The storage design is in [LLD: Memory stores](../architecture/lld-memory.md).

| Memory | Lifetime | Example content | How it's used |
|---|---|---|---|
| **Working** (`temp:`) | one turn | the query, compiled plan, step results, verdicts | Shared across workflow nodes; cleared after the turn |
| **Session** | one session | `turns`, last `plan`, `draft`, `verdict`, `last_learning` | ADK session state; visible in `adk web` |
| **User** (`user:`) | all of a user's sessions | `user:preferences = {"home_city": "User is based in Hyderabad"}` | Rendered into the synthesizer's dynamic instruction |
| **Episodic** | long-term, per user | past conversations | `recall` searches it every turn; the `load_memory` tool searches on demand |
| **Semantic** | long-term, per user | facts and preferences the user stated | `recall` gives the planner relevant facts; `recall_facts` / `remember_fact` / `forget_fact` |
| **Artifacts** | per session | `plan_results.json`, large API payloads | Full data kept out of prompts; downloadable |

## Episodic memory

- **Write:** `EpisodicMemoryPlugin.after_run_callback` sends the whole session to the memory service
  after every run.
- **Read:** `recall` calls `ctx.search_memory(question)` and includes up to 4 snippets in the
  planner prompt. The synthesizer can also call `load_memory`.
- **Backend:** `SqliteMemoryService` (FTS5) locally. In production, set `MEMORY_BACKEND=vertex` to use
  **Vertex AI Memory Bank**, which extracts and consolidates memories with an LLM.

## Semantic memory

Facts are stored only when the user **states** them. The synthesizer prompt says to call
`remember_fact` for lasting preferences and facts, not inferences.

```text
you> Remember that I'm based in Hyderabad and I prefer prices in rupees.
  · synthesizer → remember_fact(subject="home_city", fact="User is based in Hyderabad", kind="preference")
  · synthesizer → remember_fact(subject="currency", fact="User prefers prices in INR", kind="preference")

you> What's the weather like?          ← no city given
  planner sees: USER FACTS AND PREFERENCES: [{"subject": "home_city", "fact": "User is based in Hyderabad", ...}]
  plan: get_weather_forecast(city=Hyderabad)
```

Rules:

- **Supersede:** a new fact on the same subject and kind that overlaps an old one (Jaccard ≥ 0.6)
  replaces it.
- **Preferences are always included:** they come back with every search.
- **Forget:** `forget_fact(fact_id)` deletes a fact when the user asks.

The offline test `test_full_loop_revise_then_learn` checks this path: `remember_fact` writes the
fact and `user:preferences`, both visible in the next session.

## Artifacts

Every turn saves `plan_results.json` (the compiled plan and every step's full output) through the
artifact service: files under `.data/artifacts` locally, or GCS in production. `http_get_json`
saves payloads over 4 KB as their own artifacts and returns a compact preview plus the artifact
name.

## Configuration

| Setting | Effect |
|---|---|
| `MEMORY_BACKEND` | `sqlite` or `vertex` |
| `AGENT_DATA_DIR` | Where the SQLite memory and artifacts live |
| `GOOGLE_CLOUD_AGENT_ENGINE_ID`, `ARTIFACT_BUCKET` | Required for `vertex` |
