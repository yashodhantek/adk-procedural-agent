# Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Host 'x' is not in HTTP_ALLOWLIST` | A procedure or `http_get_json` called a new host | Add the host to `HTTP_ALLOWLIST` |
| Every step `skipped` | A root dependency (often `geocode_city`) failed | Check its error in `plan_results.json`; the place name may be unknown, or the source down |
| `Missing input 'x' for proc` | The planner didn't supply an input, and no dependency produces it | Add the input to the question or glossary, or a `DEPENDS_ON` edge with a mapping |
| `azure/* models need AZURE_API_BASE` | Missing provider settings | See [Configuration](../getting-started/configuration.md#provider-credentials) |
| `Non-Gemini models need LiteLLM` | The `llms` extra isn't installed | `pip install -e ".[llms]"` |
| Reasoning never turns on for Azure or TrueFoundry | `auto` can't tell what model is behind a deployment name | Set `PLANNER_REASONING=medium` (or another level) |
| `400 … reasoning_effort` | A level was forced on a model that can't reason | Set that role's reasoning to `off` |
| No web search tool | `SEARCH_PROVIDER` resolved to `none` | Set a search key or a Gemini `SEARCH_MODEL` |
| Answers always "unverified" | The critic is too strict, or the data really is missing | Check `temp:verdicts` in `adk web`; adjust `ACCEPT_SCORE`; add procedures |
| The agent forgets everything after a deploy | `AGENT_DATA_DIR` is on temporary disk | Mount a persistent volume ([Deployment](deployment.md)) |
| Too many candidate procedures | Lots of one-off multi-part questions | Run `improve.py consolidate` nightly; raise `PROMOTE_AFTER` |
| The ingestion review proposes odd edges | Generic I/O names match many procedures | Give exact `Needs:` lines (text-stated edges win), or use distinct output names |
| `Batch … was already applied` | Re-applying | Stage again if the document changed |
| `budget exhausted` message | Revise/replan loops plus tool calls hit `MAX_LLM_CALLS_PER_TURN` | Raise it, or find out why the critic keeps rejecting |
