# Tools & MCP

The synthesizer is the only role with tools. The planner and critic stay tool-free, which keeps
them fast and their structured output reliable. Full signatures are in the
[Tools reference](../reference/tools.md).

## Built-in tool families

| Family | Tools |
|---|---|
| Procedures | `run_procedure`, `find_procedures`, `teach_procedure`, `SkillToolset` (`search_skills`, `load_skill`, `load_skill_resource`) |
| Memory | `remember_fact`, `recall_facts`, `forget_fact`, `load_memory` |
| Glossary | `define_term`, `lookup_term` |
| Ingestion | `ingest_text`, `apply_ingest` |
| Data | `http_get_json` (allow-listed), `load_web_page`, `web_search` / Google Search |
| MCP | every tool from every server in `MCP_SERVERS` |

## MCP servers

```bash title=".env"
MCP_SERVERS=[{"name": "atlassian", "url": "https://mcp.atlassian.com/v2/mcp",
              "headers": {"Authorization": "Bearer <token>"}}]
```

Each entry becomes an ADK `McpToolset` (streamable HTTP) with:

- tool names prefixed by `name`
- the tool list cached for 5 minutes

A server that fails to load is skipped with a warning. The agent still starts.

**Example: Jira via Atlassian's Rovo MCP server.** The synthesizer can search and update Jira
directly. For questions people ask often, also write procedures that call the Jira REST API, so
they run deterministically and in parallel. See the [Roadmap](../roadmap.md) for first-class
`mcp_tool` procedures.

## Teaching a procedure in chat

```text
you> When I say "release health", check open P1 bugs for the release and the build status.
  · synthesizer → teach_procedure(name="release_health", description=..., steps_md=..., depends_on=[...])
```

User-taught procedures are `active` straight away (origin `user`). Their dependencies must
already exist; unknown or cyclic ones are reported back.
