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
| Approvals | `approve_action`, `reject_action`, `list_pending_actions` |
| Data | `http_get_json` (allow-listed), `load_web_page`, `web_search` / Google Search |
| MCP | every tool from every server in `MCP_SERVERS` |

## MCP servers

Configure local (stdio) and remote (streamable HTTP) servers in `mcp_servers.json` or `MCP_SERVERS`.
Each server becomes:

1. an ADK `McpToolset` for the synthesizer, with tool names prefixed by the server name and the
   tool list cached for 5 minutes, and
2. a data source that **procedure steps** can call (`MCP: server.tool …`).

Details are in [MCP & LLM steps in procedures](mcp-procedures.md). A server that fails to load
is skipped with a warning.

**Example: Jira via Atlassian's Rovo MCP server.** Add `{"name": "atlassian", "url":
"https://mcp.atlassian.com/v2/mcp", "headers": {...}}`, then write cards such as
`MCP: atlassian.searchJiraIssuesUsingJql jql="assignee = currentUser()"`. Write tools (create or
transition issues) get `Side effect: write`, so they need [approval](actions-approvals.md).

## Teaching a procedure in chat

```text
you> When I say "release health", check open P1 bugs for the release and the build status.
  · synthesizer → teach_procedure(name="release_health", description=..., steps_md=..., depends_on=[...])
```

User-taught procedures are `active` straight away (origin `user`). Their dependencies must
already exist; unknown or cyclic ones are reported back.
