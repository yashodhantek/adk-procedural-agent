# Tools

Tools available to the **synthesizer** (`harness/tools.py`, `harness/search.py`). Every call's
outcome is recorded by `ToolLearningPlugin` as source `tool:<name>`.

## Procedures

| Tool | Arguments | Returns |
|---|---|---|
| `run_procedure` | `name`, `inputs_json` (JSON object) | `{ok, outputs, error, upstream: {step: status}}`; runs dependencies too |
| `find_procedures` | `query` | `{procedures: [card + depends_on]}` |
| `teach_procedure` | `name, description, steps_md, inputs[], outputs[], depends_on[]` | `{saved, linked, unknown_or_cyclic}` |
| `search_skills` / `load_skill` / `load_skill_resource` | ADK `SkillToolset` | Procedures as Skills (see [procedural memory](../capabilities/procedural-memory.md#procedures-as-adk-skills)) |

## Memory

| Tool | Arguments | Returns |
|---|---|---|
| `remember_fact` | `subject, fact, kind` (`preference`/`fact`/`domain`) | `{stored: id}`; preferences are also mirrored to `user:preferences` |
| `recall_facts` | `query` | `{facts: [...]}` (preferences always included) |
| `forget_fact` | `fact_id` | `{deleted: bool}` |
| `load_memory` | `query` (ADK built-in) | Episodic memories |

## Glossary

| Tool | Arguments | Returns |
|---|---|---|
| `define_term` | `term, kind, definition, aliases[], applies_to[], related_procedures[]` | `{ok, term, kind}` |
| `lookup_term` | `text` (a term or a sentence) | `{matches: [...]}` |

## Ingestion

| Tool | Arguments | Returns |
|---|---|---|
| `ingest_text` | `text, source_name` | `{ok, batch_id, review, edges_needing_confirmation}`; nothing is saved yet |
| `apply_ingest` | `batch_id, approve_edges[]` (`["all"]` allowed) | Apply summary |

## Approvals

| Tool | Arguments | Returns |
|---|---|---|
| `approve_action` | `code` | Runs the parked call **only if the user's latest message contains the code** |
| `reject_action` | `code` | Discards it |
| `list_pending_actions` | — | This user's parked actions with previews |

## Data

| Tool | Arguments | Returns |
|---|---|---|
| `http_get_json` | `url, params_json` | `{ok, data (compacted), full_payload_artifact}`; the host must be allow-listed |
| `load_web_page` | `url` (ADK built-in) | Page text |
| `web_search` | `query` | `{ok, provider, results: [{title, url, snippet, published}]}` |
| Google Search agent tool | `request` | Grounded answer (when `SEARCH_PROVIDER` resolves to `gemini`) |
| MCP tools | per server | From `MCP_SERVERS`, prefixed with the server name |
