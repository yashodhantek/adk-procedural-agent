# Configuration

All settings are environment variables, usually set in `.env`. They are read once at start-up by
`procedural_agent/config.py` (agent settings) and `procedural_agent/llm.py` (provider credentials).

## Models

| Variable | Default | Meaning |
|---|---|---|
| `AGENT_MODEL` | `gemini-3.5-flash` | Synthesizer, the agent that writes answers and calls tools |
| `PLANNER_MODEL` | `gemini-3.1-pro` | Planner, which turns a question into a plan |
| `CRITIC_MODEL` | `gemini-3.5-flash` | Critic, which verifies the draft |
| `LEARNER_MODEL` | `gemini-3.5-flash` | Learning distiller and the ingestion extractor |
| `SUMMARIZER_MODEL` | `gemini-3.5-flash` | Event compaction summaries |
| `SEARCH_MODEL` | *(empty)* | Gemini model for Google Search grounding, or an OpenAI search model |

Each value is a **model spec**, such as `azure/gpt-4o-prod`, `truefoundry/openai-main/gpt-5` or
`anthropic/claude-sonnet-4-5`. Join specs with `|` for a fallback chain. See
[Multiple LLM providers](../capabilities/multi-llm.md).

!!! warning "Model names change"
    The Gemini defaults are placeholders that match ADK 2.15's own defaults. Check them against the
    current model list for your provider.

## Provider credentials

| Variable | Used by |
|---|---|
| `GOOGLE_API_KEY` or `GOOGLE_GENAI_USE_VERTEXAI` + `GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION` | Gemini |
| `OPENAI_API_KEY`, `OPENAI_BASE_URL` (optional) | `openai/…` |
| `AZURE_API_KEY`, `AZURE_API_BASE`, `AZURE_API_VERSION` (also read as `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `OPENAI_API_VERSION`) | `azure/…` |
| `TFY_BASE_URL` (gateway = `$TFY_BASE_URL/api/llm`) or `TFY_GATEWAY_URL`, `TFY_API_KEY`, `TFY_EXTRA_HEADERS` (JSON) | `truefoundry/…` |
| `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_KEY`, `OPENAI_COMPAT_HEADERS` (JSON) | `openai_compatible/…` |
| Provider's own variables (for example `ANTHROPIC_API_KEY`, AWS credentials) | anything else LiteLLM supports |

## Reasoning and caching

| Variable | Default | Meaning |
|---|---|---|
| `PLANNER_REASONING` | `auto` | `off`, `auto`, `minimal`, `low`, `medium` or `high` |
| `AGENT_REASONING` | `auto` | Same, for the synthesizer |
| `CRITIC_REASONING` | `off` | Same, for the critic |
| `PLAN_REACT_FALLBACK` | `true` | Give a non-reasoning synthesizer ADK's `PlanReActPlanner` |
| `PROMPT_CACHE_HINTS` | `true` | Send `prompt_cache_key` (OpenAI, Azure, TrueFoundry) and `cache_control` (Anthropic) |
| `CONTEXT_CACHE` | `true` | Gemini context caching (applies only when `AGENT_MODEL` is Gemini) |

## Harness loop

| Variable | Default | Meaning |
|---|---|---|
| `ACCEPT_SCORE` | `0.75` | The critic's score at or above which a draft is accepted |
| `MAX_REVISIONS` | `2` | Answer rewrites allowed per turn |
| `MAX_REPLANS` | `1` | Re-plans allowed per turn (when the critic reports missing data) |
| `MAX_LLM_CALLS_PER_TURN` | `40` | Budget guard: model calls allowed per turn |
| `STEP_TIMEOUT_S` | `20` | HTTP timeout per procedure call (the whole step gets 3×) |
| `MAX_PARALLEL_STEPS` | `8` | Concurrency cap within one plan level |

## Learning

| Variable | Default | Meaning |
|---|---|---|
| `LEARNING_ENABLED` | `true` | Run the `learn` node after each answer |
| `LEARNER_MODE` | `llm` | `llm` (model-written procedures and lessons) or `heuristic` (no model calls) |
| `PROMOTE_AFTER` | `3` | Successes before a candidate procedure becomes active |
| `DEPRECATE_BELOW` | `0.35` | Reliability below which a procedure with at least 4 runs is retired |
| `PLAYBOOK_SIZE` | `12` | Playbook bullets injected per prompt |

## Context management

| Variable | Default | Meaning |
|---|---|---|
| `COMPACTION_INTERVAL` | `6` | Summarise after this many new invocations |
| `COMPACTION_OVERLAP` | `1` | Invocations shared between consecutive summaries |
| `COMPACTION_TOKEN_THRESHOLD` | `60000` | Also summarise when the prompt passes this many tokens |
| `COMPACTION_KEEP_EVENTS` | `12` | Raw events kept after a token-based compaction |
| `CONTEXT_KEEP_INVOCATIONS` | `20` | `ContextFilterPlugin` hard cap |

## Data sources and tools

| Variable | Default | Meaning |
|---|---|---|
| `HTTP_ALLOWLIST` | the six seed API hosts | Hosts procedures and `http_get_json` may call (`*` turns the check off) |
| `SEARCH_PROVIDER` | `auto` | `auto`, `gemini`, `tavily`, `exa`, `brave`, `openai` or `none` |
| `TAVILY_API_KEY`, `EXA_API_KEY`, `BRAVE_API_KEY` | | Search provider keys |
| `SEARCH_MAX_RESULTS` | `5` | Results returned by `web_search` |
| `MCP_SERVERS` | `[]` | JSON list of `{"name", "url", "headers"}` for streamable-HTTP MCP servers |

## Storage

| Variable | Default | Meaning |
|---|---|---|
| `AGENT_DATA_DIR` | `.data` | SQLite databases, artifacts, prompt versions, ingest reports |
| `MEMORY_BACKEND` | `sqlite` | `sqlite` (local) or `vertex` (Agent Engine sessions, Memory Bank, GCS) |
| `GOOGLE_CLOUD_AGENT_ENGINE_ID` | | Required for `vertex` |
| `ARTIFACT_BUCKET` | | Required for `vertex` |

## Observability and security

| Variable | Meaning |
|---|---|
| `ADK_LOGGING=1` | Add ADK's `LoggingPlugin` |
| `ENABLE_TRACING=1` | Add `AutoTracingPlugin` (OpenTelemetry spans per node) |
| `TOOL_CALL_HMAC_KEY` | Add `ToolCallIntegrityPlugin` with this key |
