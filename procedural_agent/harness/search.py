"""Web search that works with every model provider.

SEARCH_PROVIDER
  gemini  Google Search grounding (ADK GoogleSearchAgentTool; needs a Gemini SEARCH_MODEL)
  tavily  Tavily /search            TAVILY_API_KEY
  exa     Exa /search               EXA_API_KEY
  brave   Brave Web Search          BRAVE_API_KEY
  openai  OpenAI search model via LiteLLM web_search_options  (SEARCH_MODEL=openai/gpt-4o-search-preview)
  none    no web search
  auto    gemini if a Gemini model is available, else the first of tavily/exa/brave with a key,
          else openai if SEARCH_MODEL is an OpenAI model, else none

The HTTP providers return the same shape: {"provider", "results": [{title, url, snippet, published}]}.
MCP search servers (configured in MCP_SERVERS) work alongside any of these.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from .. import llm
from ..config import settings
from .executor import compact, fetcher

log = logging.getLogger(__name__)

_ENDPOINTS = {
    "tavily": "https://api.tavily.com/search",
    "exa": "https://api.exa.ai/search",
    "brave": "https://api.search.brave.com/res/v1/web/search",
}
_KEYS = {"tavily": "TAVILY_API_KEY", "exa": "EXA_API_KEY", "brave": "BRAVE_API_KEY"}


def _gemini_search_model() -> str:
  if settings.search_model and llm.is_gemini(settings.search_model):
    return settings.search_model.split("|")[0]
  primary = settings.model.split("|")[0]
  return primary if llm.is_gemini(primary) else ""


def choose_provider() -> str:
  p = settings.search_provider.lower()
  if p != "auto":
    return p
  if _gemini_search_model():
    return "gemini"
  for name in ("tavily", "exa", "brave"):
    if os.environ.get(_KEYS[name]):
      return name
  if settings.search_model.split("|")[0].strip().startswith(("openai/", "truefoundry/")):
    return "openai"
  return "none"


async def _http_search(provider: str, query: str, n: int) -> list[dict]:
  key = os.environ.get(_KEYS[provider], "")
  if not key:
    raise RuntimeError(f"{_KEYS[provider]} is not set")
  if provider == "tavily":
    data = await fetcher.request_json("POST", _ENDPOINTS["tavily"], check=False,
                                      headers={"Authorization": f"Bearer {key}"},
                                      json={"query": query[:400], "max_results": n, "search_depth": "basic"})
    return [{"title": r.get("title"), "url": r.get("url"), "snippet": r.get("content"),
             "published": r.get("published_date")} for r in data.get("results", [])]
  if provider == "exa":
    data = await fetcher.request_json("POST", _ENDPOINTS["exa"], check=False, headers={"x-api-key": key},
                                      json={"query": query, "type": "auto", "numResults": n,
                                            "contents": {"highlights": True}})
    return [{"title": r.get("title"), "url": r.get("url"),
             "snippet": " … ".join(r.get("highlights") or []) or (r.get("text") or "")[:400],
             "published": r.get("publishedDate")} for r in data.get("results", [])]
  data = await fetcher.request_json("GET", _ENDPOINTS["brave"], check=False,
                                    headers={"X-Subscription-Token": key, "Accept": "application/json"},
                                    params={"q": query, "count": n})
  return [{"title": r.get("title"), "url": r.get("url"), "snippet": r.get("description"),
           "published": r.get("page_age") or r.get("age")} for r in (data.get("web") or {}).get("results", [])]


async def _openai_search(query: str) -> list[dict]:
  import litellm
  s = llm.parse_chain(settings.search_model)[0]
  resp = await litellm.acompletion(model=s.litellm_model, messages=[{"role": "user", "content": query}],
                                   web_search_options={"search_context_size": "medium"}, **s.kwargs)
  msg = resp.choices[0].message
  cites = []
  for a in getattr(msg, "annotations", None) or []:
    c = a.get("url_citation", a) if isinstance(a, dict) else getattr(a, "url_citation", a)
    get = c.get if isinstance(c, dict) else lambda k, d=None: getattr(c, k, d)
    cites.append({"title": get("title"), "url": get("url"), "snippet": None, "published": None})
  return [{"title": "answer", "url": None, "snippet": msg.content, "published": None}] + cites


async def web_search(query: str) -> dict:
  """Search the web for current information no procedure covers. Cite the URLs you use.

  Args:
    query: A focused search query.
  """
  provider = choose_provider()
  n = settings.search_max_results
  try:
    if provider in _ENDPOINTS:
      results = await _http_search(provider, query, n)
    elif provider == "openai":
      results = await _openai_search(query)
    else:
      return {"ok": False, "error": f"No web search provider configured (SEARCH_PROVIDER={provider})"}
  except Exception as e:  # noqa: BLE001
    return {"ok": False, "provider": provider, "error": f"{type(e).__name__}: {e}"}
  return {"ok": True, "provider": provider, "results": compact(results[:n])}


def search_tools() -> list[Any]:
  provider = choose_provider()
  if provider == "none":
    log.info("Web search disabled (SEARCH_PROVIDER resolved to none)")
    return []
  if provider == "gemini":
    model = _gemini_search_model()
    if not model:
      log.warning("SEARCH_PROVIDER=gemini needs a Gemini SEARCH_MODEL or AGENT_MODEL; search disabled")
      return []
    from google.adk.tools.google_search_agent_tool import GoogleSearchAgentTool, create_google_search_agent
    return [GoogleSearchAgentTool(create_google_search_agent(model))]
  return [web_search]
