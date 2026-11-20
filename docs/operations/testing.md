# Testing

```bash
python -m pytest -q        # 38 tests, offline, about 10 s
```

| File | Covers |
|---|---|
| `tests/test_memory.py` | Closure + parallel levels, composite expansion, unknown → adhoc, cycles, path language, safe eval, failure/skip semantics + reliability, ranking, fact supersede, lesson dedupe, playbook pruning |
| `tests/test_e2e.py` | Full workflow: tool call, revise loop, induction, Reflexion, semantic + `user:` memory, plan cache, episodic memory, artifacts; reuse → promotion; re-plan; partial failure is not learned |
| `tests/test_ingest.py` | Glossary resolution and normalisation, term merging; card pipeline end to end (canonicalisation, verified call, confirmed/review edges, apply, composite run); free-text resolution, dedupe, cycle rejection; blocked hosts and undeclared inputs |
| `tests/test_llm.py` | Spec parsing for every provider, model types, `FallbackLlm`, `complete_json` fallback via LiteLLM, **full workflow on LiteLLM models** |
| `tests/test_mcp_procedures.py` | A **real local stdio MCP server**: cards → MCP/LLM/write procedures, live verification during ingestion, parallel run, parked write with exact preview, wrong-user / repeat / expired approvals, the approve tool needing the user's own words, dependents waiting, unconfigured servers blocked, writes never learned |
| `tests/test_features.py` | Reasoning resolution and parameters, per-role agents (BuiltIn / PlanReAct / effort), stable cacheable prefix + cache key, every search provider, `auto` selection, OpenAI search, PlanReAct answer extraction |

## Test doubles

- `tests/fakes.py::ScriptedLlm` plays the planner, synthesizer and critic, recognising each role
  from its static instruction.
- `mock_transport()` returns recorded API payloads, and can fail chosen hosts.
- LiteLLM `mock_response` and a capturing `llm_client` test the non-Gemini path without a network.

## Docs examples are tests too

`scripts/generate_doc_examples.py` runs ten scenarios through the real code. When a behaviour
changes, regenerate them and read the diff. That's how two learning and ingestion bugs were
found and fixed (see [Example 7](../examples/failure.md)).
