# Signal (techintel) pack

| File | What it is |
|---|---|
| `techintel_mcp.py` | MCP server for the Signal platform: `get_trends`, `get_radar`, `get_recommendations`, `list_concepts`, `get_concept`, `list_reports`, `search` (read) and `save_brief` (write) |
| `procedures.md` | 9 procedure cards + 2 glossary terms, including `techintel_brief` (5 parallel MCP reads → LLM summary) and `techintel_save_brief` (approval-gated write) |
| `mcp_servers.json.example` | Server config: copy to the repo root as `mcp_servers.json` |
| `sample-brief-demo-corpus.md` | A brief produced against a local Signal with its synthetic demo corpus |

```bash
cp packs/techintel/mcp_servers.json.example mcp_servers.json
export TECHINTEL_URL=https://intel.yashodhantek.com TECHINTEL_EMAIL=you@... TECHINTEL_PASSWORD=...
python scripts/ingest.py packs/techintel/procedures.md --apply
python scripts/run_procedure.py techintel_save_brief --user srini   # prints an approval code
python scripts/approve.py <CODE> --user srini                         # writes ~/techintel-briefs/<date>-signal-brief.md
```

Test the server on its own with the MCP inspector:
`npx @modelcontextprotocol/inspector python packs/techintel/techintel_mcp.py`.
Use an account with read access; an analyst role is enough.
