"""End-to-end run of the full ADK 2.x workflow with a scripted model and mock APIs."""

from __future__ import annotations

import asyncio
import os
import tempfile

os.environ.setdefault("AGENT_DATA_DIR", tempfile.mkdtemp(prefix="pa_e2e_"))
os.environ["LEARNER_MODE"] = "heuristic"
os.environ["SEARCH_PROVIDER"] = "none"
os.environ.setdefault("GOOGLE_API_KEY", "offline-test")

from google.adk import Runner  # noqa: E402
from google.adk.apps import App  # noqa: E402
from google.adk.artifacts import InMemoryArtifactService  # noqa: E402
from google.adk.memory import InMemoryMemoryService  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from procedural_agent.agent import build_workflow  # noqa: E402
from procedural_agent.harness import executor  # noqa: E402
from procedural_agent.harness.plugins import build_plugins  # noqa: E402
from procedural_agent.memory import agent_memory  # noqa: E402
from fakes import ScriptedLlm, mock_transport  # noqa: E402

PLAN = {
    "intent": "weather air quality and currency conversion", "domain": "travel",
    "steps": [
        {"id": "s1", "procedure": "get_weather_forecast", "inputs": [{"name": "city", "value": "Hyderabad"}]},
        {"id": "s2", "procedure": "get_air_quality", "inputs": [{"name": "city", "value": "Hyderabad"}]},
        {"id": "s3", "procedure": "convert_amount", "inputs": [
            {"name": "amount", "value": "100"}, {"name": "from_currency", "value": "USD"},
            {"name": "to_currency", "value": "INR"}]},
    ],
    "answer_strategy": "weather + AQI summary, then conversion",
}
QUESTION = "What's the weather and air quality in Hyderabad, and what is 100 USD in INR?"


async def run_turn(llm: ScriptedLlm, session_id: str, text: str = QUESTION):
  executor.fetcher.transport = mock_transport()
  wf = build_workflow(model=llm, planner_model=llm, critic_model=llm)
  app = App(name="procedural_agent", root_agent=wf, plugins=build_plugins())
  runner = Runner(app=app, session_service=SESSIONS, memory_service=MEMORY,
                  artifact_service=ARTIFACTS, auto_create_session=True)
  final = None
  async for ev in runner.run_async(user_id="srini", session_id=session_id,
                                   new_message=types.Content(role="user", parts=[types.Part(text=text)])):
    if ev.content and ev.content.parts and ev.content.parts[0].text and ev.author == "procedural_agent":
      final = ev.content.parts[0].text
  session = await SESSIONS.get_session(app_name="procedural_agent", user_id="srini", session_id=session_id)
  return final, session


SESSIONS, MEMORY, ARTIFACTS = InMemorySessionService(), InMemoryMemoryService(), InMemoryArtifactService()


def test_full_loop_revise_then_learn():
  llm = ScriptedLlm(plan=PLAN, critic_script=[
      {"ok": False, "score": 0.4, "issues": ["State the data timestamp"], "missing_data": False},
      {"ok": True, "score": 0.95, "issues": [], "missing_data": False}],
      synth_tool_call={"name": "remember_fact", "args": {
          "subject": "home_city", "fact": "User is based in Hyderabad", "kind": "preference"}})
  final, session = asyncio.run(run_turn(llm, "s1"))
  roles = [r for r, _ in llm.calls]
  # planner -> synthesizer(tool call) -> synthesizer -> critic(reject) -> synthesizer(revise) -> critic(accept)
  assert roles[0] == "planner" and roles.count("critic") == 2, roles
  assert final and final.startswith("Revised:"), final
  mem = agent_memory()
  # self-learning: composite procedure induced from the multi-procedure run
  learned = [p for p in mem.kg.all() if p.origin == "learned"]
  assert learned and learned[0].status == "candidate", mem.kg.stats()
  assert set(mem.kg.parts(learned[0].name)) == {"get_weather_forecast", "get_air_quality", "convert_amount"}
  # reflexion lesson written because the first draft failed review
  assert mem.reflections.relevant("weather Hyderabad timestamp")
  # reliability stats learned for every executed procedure
  assert mem.kg.get("geocode_city").success >= 1 and mem.kg.get("get_fx_rate").success >= 1
  # semantic memory via tool + user-scoped state
  assert mem.facts.search("srini", "where am I based")
  assert "home_city" in session.state.get("user:preferences", {})
  # plan cache + learning report in state
  assert mem.kg.cached_plan(QUESTION) is not None
  assert session.state["last_learning"].get("induced")
  # episodic memory (EpisodicMemoryPlugin) and artifact memory (execute_plan)
  hits = asyncio.run(MEMORY.search_memory(app_name="procedural_agent", user_id="srini", query="Hyderabad"))
  assert hits.memories
  keys = asyncio.run(ARTIFACTS.list_artifact_keys(app_name="procedural_agent", user_id="srini", session_id="s1"))
  assert "plan_results.json" in keys


def test_cached_plan_and_promotion():
  learned = next(p for p in agent_memory().kg.all() if p.origin == "learned")
  plan = {"intent": "same thing", "domain": "travel", "steps": [{"id": "s1", "procedure": learned.name, "inputs": [
      {"name": "city", "value": "Hyderabad"}, {"name": "amount", "value": "100"},
      {"name": "from_currency", "value": "USD"}, {"name": "to_currency", "value": "INR"}]}]}
  for i in range(3):
    llm = ScriptedLlm(plan=plan, critic_script=[{"ok": True, "score": 0.9, "issues": []}])
    final, _ = asyncio.run(run_turn(llm, f"s_reuse_{i}"))
    assert final and "8400.0" in final
    # the planner prompt carried the cached plan from the first run
    assert "CACHED PLAN" in llm.calls[0][1] and '"similarity"' in llm.calls[0][1]
  assert agent_memory().kg.get(learned.name).status == "active"   # promoted after repeated success


def test_replan_when_data_missing():
  llm = ScriptedLlm(plan=PLAN, critic_script=[
      {"ok": False, "score": 0.2, "issues": ["No humidity"], "missing_data": True},
      {"ok": True, "score": 0.9, "issues": []}])
  final, _ = asyncio.run(run_turn(llm, "s_replan"))
  assert [r for r, _ in llm.calls].count("planner") == 2
  assert "REVIEW FEEDBACK" in [t for r, t in llm.calls if r == "planner"][1]
  assert final
