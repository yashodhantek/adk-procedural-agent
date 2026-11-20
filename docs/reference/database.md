# Database schema

`$AGENT_DATA_DIR/agent_memory.sqlite` (WAL mode). ADK's own services use `sessions.sqlite` and
`episodic_memory.sqlite`.

| Table | Purpose | Key columns |
|---|---|---|
| `procedures` | Procedure nodes | `name` PK, `domain`, `description`, `inputs_json`, `outputs_json`, `steps_md`, `call_json`, `status`, `origin`, `version`, `success`, `failure`, `total_latency_ms`, timestamps |
| `edges` | Graph edges | (`src`, `dst`, `type`) PK, `mapping_json`, `weight` |
| `sources` | Data sources and tools | `name` PK, `kind`, `base_url`, `success`, `failure`, `total_latency_ms` |
| `plan_cache` | Successful plans | `signature` PK, `query`, `plan_json`, `successes`, `failures` |
| `facts` | Semantic memory | `id` PK, `user_id`, `subject`, `fact`, `kind`, `confidence`; UNIQUE(`user_id`, `subject`, `fact`) |
| `lessons` | Reflexion | `id` PK, `scope`, `cue`, `lesson`, `uses` |
| `playbook` | ACE bullets | `id` PK, `section`, `bullet` UNIQUE, `helpful`, `harmful`, `active` |
| `terms` | Glossary | (`canonical`, `kind`) PK, `definition`, `domain`, `scope_json`, `format`, `unit`, `origin` |
| `term_aliases` | Glossary aliases | (`alias`, `kind`, `canonical`) PK |
| `term_links` | Concept → procedure | (`canonical`, `procedure`) PK |
| `ingest_batches` | Staged ingestion | `id` PK, `source`, `status`, `report_json` |
| `procedures_fts`, `facts_fts`, `lessons_fts` | FTS5 indexes | Searchable text |

Diagrams are in [LLD: Memory stores](../architecture/lld-memory.md) and
[LLD: Procedural graph](../architecture/lld-procedural-graph.md).

!!! tip "Multiple replicas"
    SQLite suits a single process. For several replicas, put `AGENT_DATA_DIR` on a shared volume
    with one writer, or port `SqliteStore` to Postgres (the SQL is portable apart from FTS5).
