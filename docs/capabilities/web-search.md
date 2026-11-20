# Web search

**What it does.** Gives the synthesizer current web results for anything no procedure covers. It
works the same whichever model provider you use.

## Providers

| `SEARCH_PROVIDER` | Backend | Needs |
|---|---|---|
| `gemini` | Google Search grounding (`GoogleSearchAgentTool`) | A Gemini `SEARCH_MODEL`, or a Gemini `AGENT_MODEL` |
| `tavily` | `POST https://api.tavily.com/search` (Bearer key) | `TAVILY_API_KEY` |
| `exa` | `POST https://api.exa.ai/search` (`x-api-key`, highlights) | `EXA_API_KEY` |
| `brave` | `GET https://api.search.brave.com/res/v1/web/search` (`X-Subscription-Token`) | `BRAVE_API_KEY` |
| `openai` | An OpenAI search model through LiteLLM's `web_search_options` | `SEARCH_MODEL=openai/<search model>` |
| `none` | No web search | — |
| `auto` *(default)* | The first available of: gemini → tavily → exa → brave → openai → none | — |

`auto` lets you keep Gemini **just for search** (`SEARCH_MODEL=gemini-3.5-flash`) while every other
role runs on Azure or OpenAI.

## Result shape

The HTTP providers return the same shape:

```json
{"ok": true, "provider": "tavily",
 "results": [{"title": "...", "url": "https://...", "snippet": "...", "published": "2026-11-20"}]}
```

The `openai` provider returns the model's answer first, then the cited URLs. Search APIs are
operator-chosen vendor endpoints, so they don't go through `HTTP_ALLOWLIST`.

## When the agent searches

The synthesizer prompt says to use search for `deferred` or `adhoc` steps, or as a fallback when
a procedure failed, and to cite the URLs it used. Every search call's reliability is tracked as
source `tool:web_search`.

The offline tests cover each provider with recorded responses, `auto` selection in five
configurations, and OpenAI citation parsing.
