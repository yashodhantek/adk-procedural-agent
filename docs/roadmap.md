# Roadmap

| Item | Why | Status |
|---|---|---|
| Authenticated call specs (`secret_ref` from env, Basic or Bearer) | Private APIs such as Jira, CRMs and internal services | planned |
| POST/PUT call specs with JSON bodies | JQL search, writes | planned |
| `mcp_tool` call kind + local stdio MCP servers | Procedures whose steps are MCP tools, executed and measured like HTTP ones | **done** |
| `LLM:` steps | Summarise / classify / draft inside a procedure | **done** |
| `side_effect: write` + approval gate | Writes never run without a user yes, exactly as previewed | **done** |
| Signal (techintel) MCP server + pack | Live AI-technology intelligence briefs | **done** |
| `Schedule:` field + runner | Run procedures on a timetable (today: cron + `run_procedure.py`) | planned |
| Jira pack | ~10 procedures (search, my work, sprint status, blockers, create with confirmation…) + glossary + tests | planned |
| Embedding search (hybrid with FTS5) | Better recall for paraphrased questions on large graphs | proposed |
| Postgres `SqliteStore` port | Several replicas, one shared agent memory | proposed |
| Graph UI (review queue, approve edges, see stats) | Easier curation than the CLI | proposed |
| Per-tenant graphs | One deployment, many teams | proposed |

Contributions welcome: open an issue or PR on
[GitHub](https://github.com/yashodhantek/adk-procedural-agent).
