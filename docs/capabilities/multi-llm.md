# Multiple LLM providers

**What it does.** Each role can use a different model from a different vendor, with ordered
fallback chains. One string per role configures everything.

## Spec formats

| Spec | Provider | Settings |
|---|---|---|
| `gemini-3.5-flash` | Gemini (API key or Vertex AI) | `GOOGLE_API_KEY` or `GOOGLE_GENAI_USE_VERTEXAI` |
| `openai/gpt-4.1` | OpenAI | `OPENAI_API_KEY`, optional `OPENAI_BASE_URL` |
| `azure/<deployment>` | Azure OpenAI | `AZURE_API_KEY`, `AZURE_API_BASE`, `AZURE_API_VERSION` |
| `truefoundry/<provider-account>/<model>` | TrueFoundry AI Gateway (OpenAI-compatible) | `TFY_BASE_URL` or `TFY_GATEWAY_URL`, `TFY_API_KEY`, optional `TFY_EXTRA_HEADERS` |
| `openai_compatible/<model>` | vLLM, LM Studio, a LiteLLM proxy… | `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_KEY` |
| `anthropic/…`, `bedrock/…`, `ollama_chat/…`, `vertex_ai/…` | anything LiteLLM supports | that provider's own variables |

Azure OpenAI **through TrueFoundry** is `truefoundry/<your-azure-account>/<model>`, using the
provider-account name shown in TrueFoundry's playground, for example
`truefoundry/azure-openai-main/gpt-4o`.

## Roles

| Variable | Role | Suggested model |
|---|---|---|
| `PLANNER_MODEL` | Plans over the graph | The strongest reasoning model you have |
| `AGENT_MODEL` | Answers and calls tools | A fast, tool-reliable model |
| `CRITIC_MODEL` | Verifies drafts | A small, strict model |
| `LEARNER_MODEL` | Induces procedures, lessons, playbook; ingestion extraction | A small model |
| `SUMMARIZER_MODEL` | Compaction summaries | The cheapest model |
| `SEARCH_MODEL` | Google Search grounding or an OpenAI search model | Gemini Flash, or an OpenAI search model |

## Fallback chains

```bash
AGENT_MODEL="azure/gpt-4o-prod|truefoundry/azure-openai-main/gpt-4o|gemini-3.5-flash"
```

If Azure fails before producing any output, the same request goes to TrueFoundry, and then to
Gemini. A model that has already started answering is never swapped mid-answer. Structured-output
calls (learner, ingestion) use the same chains.

## What changes by provider

| Capability | How it adapts |
|---|---|
| [Reasoning](reasoning.md) | Gemini thinking level, or `reasoning_effort`, or the plan-then-act fallback |
| [Prompt caching](prompt-caching.md) | Gemini context cache, `prompt_cache_key`, or Anthropic `cache_control` |
| [Web search](web-search.md) | Google grounding, or Tavily, Exa, Brave or OpenAI search |

## Real example: how a mixed setup resolves

--8<-- "ex_providers.md"

The offline test `test_workflow_runs_on_litellm_models` runs the whole workflow on LiteLLM models
(a TrueFoundry planner, an Azure synthesizer and an OpenAI critic, with mocked responses). It
checks that structured `Plan` and `Verdict` output, glossary normalisation and execution all
work.
