"""Provider layer: spec parsing, fallback, LiteLLM through the real workflow (offline mocks)."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile

os.environ.setdefault("AGENT_DATA_DIR", tempfile.mkdtemp(prefix="pa_llm_"))
os.environ["LEARNER_MODE"] = "heuristic"

import pytest  # noqa: E402
from google.adk import Runner  # noqa: E402
from google.adk.apps import App  # noqa: E402
from google.adk.models.lite_llm import LiteLlm  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from fakes import ScriptedLlm, mock_transport  # noqa: E402
from procedural_agent import llm  # noqa: E402
from procedural_agent.agent import build_workflow  # noqa: E402
from procedural_agent.harness import executor  # noqa: E402


@pytest.fixture()
def env(monkeypatch):
  for k, v in {"TFY_BASE_URL": "https://acme.truefoundry.cloud", "TFY_API_KEY": "tfy-123",
               "TFY_EXTRA_HEADERS": '{"X-TFY-METADATA": "{\\"app\\": \\"agent\\"}"}',
               "AZURE_API_KEY": "az-key", "AZURE_API_BASE": "https://acme.openai.azure.com",
               "AZURE_API_VERSION": "2025-04-01-preview", "OPENAI_API_KEY": "sk-x"}.items():
    monkeypatch.setenv(k, v)


def test_spec_parsing(env):
  g = llm.parse("gemini-3.5-flash")
  assert g.is_gemini
  t = llm.parse("truefoundry/azure-openai-main/gpt-4o")
  assert t.litellm_model == "openai/azure-openai-main/gpt-4o"
  assert t.kwargs["api_base"] == "https://acme.truefoundry.cloud/api/llm" and t.kwargs["api_key"] == "tfy-123"
  assert "X-TFY-METADATA" in t.kwargs["extra_headers"]
  a = llm.parse("azure/my-gpt4o-deployment")
  assert a.kwargs == {"api_key": "az-key", "api_base": "https://acme.openai.azure.com",
                      "api_version": "2025-04-01-preview"}
  assert llm.parse("openai/gpt-4.1").kwargs["api_key"] == "sk-x"
  assert llm.parse("anthropic/claude-sonnet-4-5").provider == "litellm"
  chain = llm.parse_chain("azure/x | truefoundry/openai-main/gpt-4o | gemini-3.5-flash")
  assert [c.provider for c in chain] == ["azure", "truefoundry", "gemini"]
  assert llm.is_gemini("gemini-3.5-flash|openai/gpt-4o") and not llm.is_gemini("openai/gpt-4o|gemini-3.5-flash")
  assert all("***" == d.get("api_key", "***") for d in llm.describe("azure/x|openai/gpt-4o"))
  with pytest.raises(ValueError):
    llm.parse("gpt-4o")                     # provider prefix required


def test_build_model_types(env):
  assert isinstance(llm.build_model("truefoundry/openai-main/gpt-4o"), LiteLlm)
  assert isinstance(llm.build_model("azure/x|openai/gpt-4o"), llm.FallbackLlm)


class Boom(ScriptedLlm):
  async def generate_content_async(self, llm_request, stream=False):
    raise ConnectionError("azure down")
    yield  # pragma: no cover


def test_fallback_chain_moves_on():
  ok = ScriptedLlm(plan={"intent": "x", "steps": []}, critic_script=[{"ok": True, "score": 1}])
  fb = llm.FallbackLlm([Boom(model="azure/x"), ok])
  from google.adk.models.llm_request import LlmRequest
  req = LlmRequest(contents=[types.Content(role="user", parts=[types.Part(text="hi")])],
                   config=types.GenerateContentConfig(system_instruction="You are the PLANNER"))

  async def run():
    return [r async for r in fb.generate_content_async(req)]
  out = asyncio.run(run())
  assert json.loads(out[0].content.parts[0].text)["intent"] == "x"


class Small(BaseModel):
  answer: str
  n: int


def test_complete_json_via_litellm_with_fallback(env, monkeypatch):
  import litellm
  calls = []
  real = litellm.acompletion

  async def fake(**kw):
    calls.append(kw["model"])
    if kw["model"].startswith("azure/"):
      raise litellm.exceptions.APIConnectionError("down", llm_provider="azure", model=kw["model"])
    return await real(**kw, mock_response='```json\n{"answer": "ok", "n": 2}\n```')
  monkeypatch.setattr(litellm, "acompletion", fake)
  out = asyncio.run(llm.complete_json("azure/x|truefoundry/openai-main/gpt-4o", "q", Small))
  assert out == {"answer": "ok", "n": 2}
  assert calls[0].startswith("azure/") and calls[-1] == "openai/openai-main/gpt-4o"


def test_workflow_runs_on_litellm_models(env):
  """Full graph with LiteLlm models (mock_response): planner/critic use structured output."""
  plan = {"intent": "fx", "domain": "finance", "steps": [{"id": "s1", "procedure": "convert_amount", "inputs": [
      {"name": "amount", "value": "100"}, {"name": "from_currency", "value": "dollars"},
      {"name": "to_currency", "value": "rupees"}]}], "answer_strategy": "one line"}
  planner = llm.build_model("truefoundry/azure-openai-main/gpt-4o", mock_response=json.dumps(plan))
  synth = llm.build_model("azure/gpt-4o-deploy", mock_response="100 USD = 8400.0 INR (rate 84.0, 2026-11-20).")
  critic = llm.build_model("openai/gpt-4.1-mini", mock_response=json.dumps({"ok": True, "score": 0.9, "issues": []}))
  executor.fetcher.transport = mock_transport()
  wf = build_workflow(model=synth, planner_model=planner, critic_model=critic, with_tools=False)
  sessions = InMemorySessionService()
  runner = Runner(app=App(name="procedural_agent", root_agent=wf), session_service=sessions, auto_create_session=True)

  async def run():
    final = None
    async for ev in runner.run_async(user_id="u", session_id="s", new_message=types.Content(
        role="user", parts=[types.Part(text="100 dollars in rupees?")])):
      if ev.author == "procedural_agent" and ev.content and ev.content.parts and ev.content.parts[0].text:
        final = ev.content.parts[0].text
    return final, await sessions.get_session(app_name="procedural_agent", user_id="u", session_id="s")
  final, session = asyncio.run(run())
  assert "8400.0" in final
  assert session.state["plan"]["steps"][0]["procedure"] == "convert_amount"
  assert session.state["verdict"]["ok"] is True
