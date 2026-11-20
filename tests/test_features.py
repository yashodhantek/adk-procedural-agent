"""Reasoning, prompt caching and web search across providers (offline)."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import tempfile

os.environ.setdefault("AGENT_DATA_DIR", tempfile.mkdtemp(prefix="pa_feat_"))
os.environ["LEARNER_MODE"] = "heuristic"

import httpx  # noqa: E402
import pytest  # noqa: E402
from google.adk import Agent, Runner  # noqa: E402
from google.adk.planners import BuiltInPlanner, PlanReActPlanner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from procedural_agent import agent as agent_mod, llm, prompts  # noqa: E402
from procedural_agent.config import settings  # noqa: E402
from procedural_agent.harness import executor, search  # noqa: E402


@pytest.fixture()
def env(monkeypatch):
  for k, v in {"TFY_BASE_URL": "https://acme.truefoundry.cloud", "TFY_API_KEY": "t",
               "AZURE_API_KEY": "a", "AZURE_API_BASE": "https://acme.openai.azure.com", "OPENAI_API_KEY": "o"}.items():
    monkeypatch.setenv(k, v)


def use(monkeypatch, module, **changes):
  new = dataclasses.replace(settings, **changes)
  monkeypatch.setattr(module, "settings", new)
  return new


# ----------------------------------------------------------------- reasoning
def test_reasoning_resolution(env):
  P = llm.parse
  assert llm.resolve_reasoning(P("openai/gpt-5"), "auto") == "medium"
  assert llm.resolve_reasoning(P("openai/gpt-4o"), "auto") is None
  assert llm.resolve_reasoning(P("truefoundry/openai-main/gpt-5"), "auto") == "medium"   # account prefix stripped
  assert llm.resolve_reasoning(P("azure/prod-chat"), "auto") is None                     # unknown deployment name
  assert llm.resolve_reasoning(P("azure/prod-chat"), "high") == "high"                   # explicit level forces it
  assert llm.resolve_reasoning(P("openai/gpt-5"), "off") is None
  with pytest.raises(ValueError):
    llm.resolve_reasoning(P("openai/gpt-5"), "extreme")


def test_provider_kwargs_reasoning_and_cache(env):
  az = llm.provider_kwargs(llm.parse("azure/prod-o4"), "planner", "high")
  assert az == {"reasoning_effort": "high", "prompt_cache_key": "procedural-agent:planner"}
  tf = llm.provider_kwargs(llm.parse("truefoundry/openai-main/gpt-5"), "synthesizer", "auto")
  assert tf["reasoning_effort"] == "medium" and tf["extra_body"] == {"prompt_cache_key": "procedural-agent:synthesizer"}
  cl = llm.provider_kwargs(llm.parse("anthropic/claude-sonnet-4-5"), "critic", "low")
  assert cl["reasoning_effort"] == "low"   # LiteLLM maps this to Anthropic extended-thinking budgets
  assert cl["cache_control_injection_points"] == [{"location": "message", "role": "system"}]
  assert llm.provider_kwargs(llm.parse("gemini-3.5-flash"), "planner", "high") == {}


def test_agents_get_reasoning_per_provider(env, monkeypatch):
  use(monkeypatch, agent_mod, planner_model="azure/prod-o4", planner_reasoning="high",
      model="openai/gpt-4o", agent_reasoning="auto", critic_model="gemini-3.5-flash", critic_reasoning="low")
  planner, synth, critic = agent_mod.build_agents(with_tools=False)
  assert planner.model._additional_args["reasoning_effort"] == "high" and planner.planner is None
  assert synth.model._additional_args.get("reasoning_effort") is None
  assert isinstance(synth.planner, PlanReActPlanner)             # non-reasoning model: prompted plan/act
  assert isinstance(critic.planner, BuiltInPlanner)              # Gemini: native thinking
  assert critic.planner.thinking_config.thinking_level == types.ThinkingLevel.LOW
  use(monkeypatch, agent_mod, model="openai/gpt-5", agent_reasoning="auto")
  _, synth, _ = agent_mod.build_agents(with_tools=False)
  assert synth.model._additional_args["reasoning_effort"] == "medium" and synth.planner is None


# ------------------------------------------------------------------- caching
def test_static_prefix_is_stable_and_cache_key_sent(env, monkeypatch):
  import litellm
  seen = []

  class CapturingClient:   # ADK's LiteLlm calls llm_client.acompletion(...)
    async def acompletion(self, model, messages, tools=None, **kw):
      seen.append({"messages": messages, **kw})
      return await litellm.acompletion(model=model, messages=messages, mock_response="ok")

  model = llm.build_model("azure/prod-chat", role="synthesizer")
  model.llm_client = CapturingClient()
  a = Agent(name="synthesizer", model=model, static_instruction=prompts.split("synthesizer")[0],
            instruction=agent_mod._dynamic_instruction("synthesizer"))
  runner = Runner(app_name="t", agent=a, session_service=InMemorySessionService(), auto_create_session=True)

  async def turn(sid, playbook):
    await runner.session_service.create_session(app_name="t", user_id="u", session_id=sid,
                                                state={"temp:playbook": playbook})
    async for _ in runner.run_async(user_id="u", session_id=sid,
                                    new_message=types.Content(role="user", parts=[types.Part(text="hi")])):
      pass
  asyncio.run(turn("a", "- bullet one"))
  asyncio.run(turn("b", "- a different bullet"))
  sys_a = [m for m in seen[0]["messages"] if m["role"] == "system"][0]["content"]
  sys_b = [m for m in seen[1]["messages"] if m["role"] == "system"][0]["content"]
  assert sys_a == sys_b and "You are the SYNTHESIZER" in str(sys_a)   # identical cacheable prefix
  assert "Playbook" not in str(sys_a)                                  # learned content is not in it
  assert seen[0]["prompt_cache_key"] == "procedural-agent:synthesizer"


# -------------------------------------------------------------------- search
def _search_api(req: httpx.Request) -> httpx.Response:
  if req.url.host == "api.tavily.com":
    assert req.headers["authorization"] == "Bearer tv-key"
    return httpx.Response(200, json={"results": [{"title": "T", "url": "https://t.example", "content": "tavily hit"}]})
  if req.url.host == "api.exa.ai":
    assert req.headers["x-api-key"] == "exa-key" and json.loads(req.content)["contents"] == {"highlights": True}
    return httpx.Response(200, json={"results": [{"title": "E", "url": "https://e.example", "highlights": ["exa hit"]}]})
  if req.url.host == "api.search.brave.com":
    assert req.headers["x-subscription-token"] == "br-key" and req.url.params["q"] == "news"
    return httpx.Response(200, json={"web": {"results": [{"title": "B", "url": "https://b.example", "description": "brave hit"}]}})
  return httpx.Response(404)


@pytest.mark.parametrize("provider,key_env,key,snippet", [
    ("tavily", "TAVILY_API_KEY", "tv-key", "tavily hit"),
    ("exa", "EXA_API_KEY", "exa-key", "exa hit"),
    ("brave", "BRAVE_API_KEY", "br-key", "brave hit"),
])
def test_http_search_providers(monkeypatch, provider, key_env, key, snippet):
  monkeypatch.setenv(key_env, key)
  use(monkeypatch, search, search_provider=provider)
  executor.fetcher.transport = httpx.MockTransport(_search_api)
  out = asyncio.run(search.web_search("news"))
  assert out["ok"] and out["provider"] == provider and out["results"][0]["snippet"] == snippet


def test_auto_provider_selection(monkeypatch):
  for k in ("TAVILY_API_KEY", "EXA_API_KEY", "BRAVE_API_KEY"):
    monkeypatch.delenv(k, raising=False)
  use(monkeypatch, search, search_provider="auto", model="gemini-3.5-flash", search_model="")
  assert search.choose_provider() == "gemini"
  use(monkeypatch, search, search_provider="auto", model="azure/x", search_model="")
  assert search.choose_provider() == "none" and search.search_tools() == []
  monkeypatch.setenv("EXA_API_KEY", "k")
  assert search.choose_provider() == "exa" and search.search_tools() == [search.web_search]
  use(monkeypatch, search, search_provider="auto", model="azure/x", search_model="gemini-3.5-flash")
  assert search.choose_provider() == "gemini"   # Gemini only for search, everything else on Azure
  monkeypatch.delenv("EXA_API_KEY")
  use(monkeypatch, search, search_provider="auto", model="azure/x", search_model="openai/gpt-4o-search-preview")
  assert search.choose_provider() == "openai"


def test_openai_search_via_litellm(env, monkeypatch):
  import litellm
  use(monkeypatch, search, search_provider="openai", search_model="openai/gpt-4o-search-preview")

  class Msg:
    content = "Answer with sources"
    annotations = [{"type": "url_citation", "url_citation": {"title": "Src", "url": "https://s.example"}}]

  async def fake(**kw):
    assert kw["web_search_options"] == {"search_context_size": "medium"}
    return type("R", (), {"choices": [type("C", (), {"message": Msg()})()]})()
  monkeypatch.setattr(litellm, "acompletion", fake)
  out = asyncio.run(search.web_search("q"))
  assert out["ok"] and out["results"][1]["url"] == "https://s.example"


def test_plan_react_keeps_only_the_final_answer():
  from google.adk.models.lite_llm import LiteLlm
  a = Agent(name="synthesizer", planner=PlanReActPlanner(), instruction="answer", output_key="draft",
            model=LiteLlm(model="openai/gpt-4o", api_key="x",
                          mock_response="/*PLANNING*/\n1. use step results\n/*FINAL_ANSWER*/\n100 USD = 8400.0 INR."))
  sessions = InMemorySessionService()
  runner = Runner(app_name="t", agent=a, session_service=sessions, auto_create_session=True)

  async def go():
    async for _ in runner.run_async(user_id="u", session_id="s",
                                    new_message=types.Content(role="user", parts=[types.Part(text="q")])):
      pass
    return (await sessions.get_session(app_name="t", user_id="u", session_id="s")).state["draft"]
  assert asyncio.run(go()).strip() == "100 USD = 8400.0 INR."
