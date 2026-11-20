"""Regenerate the worked examples in the documentation from real runs of the code.

  python scripts/generate_doc_examples.py

Every scenario runs through the real ADK 2.x workflow, knowledge graph, executor,
glossary, learner and ingestion pipeline. Two things are substituted so the
output is reproducible and needs no keys:
  * the LLM roles (planner / synthesizer / critic) follow a script, and
  * the public APIs return recorded sample payloads (same shape as the live APIs).
Everything else (plans compiled, dependency closure, parallel levels, glossary
normalisation, learning, promotion, ingestion review) is computed by the code.

Output: docs/snippets/*.md, included by the documentation pages.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(tempfile.mkdtemp(prefix="docs_examples_"))
os.environ.update({"AGENT_DATA_DIR": str(DATA), "LEARNER_MODE": "heuristic", "SEARCH_PROVIDER": "none",
                   "GOOGLE_API_KEY": "docs-offline"})
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import httpx  # noqa: E402
from google.adk import Runner  # noqa: E402
from google.adk.apps import App  # noqa: E402
from google.adk.artifacts import InMemoryArtifactService  # noqa: E402
from google.adk.memory import InMemoryMemoryService  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from fakes import ScriptedLlm  # noqa: E402
from procedural_agent.agent import build_workflow  # noqa: E402
from procedural_agent.harness import executor  # noqa: E402
from procedural_agent.harness.ingest import Ingestor, render_report  # noqa: E402
from procedural_agent.harness.plugins import build_plugins  # noqa: E402
from procedural_agent.memory import agent_memory  # noqa: E402

OUT = ROOT / "docs" / "snippets"
SESSIONS, MEMORY, ARTIFACTS = InMemorySessionService(), InMemoryMemoryService(), InMemoryArtifactService()
DOWN: set[str] = set()

# ------------------------------------------------------------ recorded payloads
CITIES = {"hyderabad": (17.38, 78.46, "India", "Asia/Kolkata", "Hyderabad"),
          "delhi": (28.65, 77.23, "India", "Asia/Kolkata", "Delhi"),
          "bengaluru": (12.97, 77.59, "India", "Asia/Kolkata", "Bengaluru"),
          "kathmandu": (27.70, 85.32, "Nepal", "Asia/Kathmandu", "Kathmandu")}
WEATHER = {17.38: (29.4, 41, 9.7, 0.0, 31.2, 19.8, 5), 28.65: (24.1, 38, 6.1, 0.0, 26.5, 11.9, 0),
           12.97: (23.6, 62, 11.2, 0.0, 27.8, 17.1, 20), 27.70: (15.2, 55, 4.3, 0.0, 21.0, 6.4, 0)}
AQI = {17.38: (78, 24.6, 51.0), 28.65: (212, 141.3, 238.0), 12.97: (54, 13.2, 29.5), 27.70: (156, 64.0, 98.2)}


def api(req: httpx.Request) -> httpx.Response:
  host, q = req.url.host, dict(req.url.params)
  if host in DOWN:
    return httpx.Response(503, json={"reason": "Service Unavailable"})
  if host == "geocoding-api.open-meteo.com":
    c = CITIES.get(q["name"].lower())
    return httpx.Response(200, json={"results": [{"name": c[4], "latitude": c[0], "longitude": c[1], "country": c[2],
                                                  "timezone": c[3]}]} if c else {"generationtime_ms": 0.4})
  lat = float(q.get("latitude", 0))
  if host == "api.open-meteo.com":
    t, rh, ws, pr, tmax, tmin, pp = WEATHER[lat]
    return httpx.Response(200, json={
        "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h", "precipitation": "mm"},
        "current": {"time": "2026-11-20T14:15", "temperature_2m": t, "relative_humidity_2m": rh,
                    "wind_speed_10m": ws, "precipitation": pr},
        "daily": {"time": ["2026-11-20", "2026-11-21", "2026-11-22"], "temperature_2m_max": [tmax, tmax - 0.4, tmax + 0.3],
                  "temperature_2m_min": [tmin, tmin + 0.2, tmin - 0.5], "precipitation_probability_max": [pp, pp + 5, pp]}})
  if host == "air-quality-api.open-meteo.com":
    a, p25, p10 = AQI[lat]
    return httpx.Response(200, json={"current": {"time": "2026-11-20T14:00", "us_aqi": a, "pm2_5": p25, "pm10": p10}})
  if host == "api.frankfurter.app":
    rates = {("EUR", "INR"): 97.42, ("USD", "INR"): 84.36, ("GBP", "INR"): 112.08}
    return httpx.Response(200, json={"amount": 1.0, "base": q["from"], "date": "2026-11-20",
                                     "rates": {q["to"]: rates[(q["from"], q["to"])]}})
  if host == "api.coingecko.com":
    return httpx.Response(200, json={q["ids"]: {q["vs_currencies"]: 7854210}})
  if host == "earthquake.usgs.gov":
    return httpx.Response(200, json={"metadata": {"count": 2}, "features": [
        {"properties": {"mag": 4.6, "place": "62 km NW of Kathmandu, Nepal", "time": 1763370000000}},
        {"properties": {"mag": 4.1, "place": "Gorkha district, Nepal", "time": 1762900000000}}]})
  return httpx.Response(404, json={})


executor.fetcher.transport = httpx.MockTransport(api)


# ------------------------------------------------------------------ helpers
def step(sid, proc, **inputs):
  return {"id": sid, "procedure": proc, "inputs": [{"name": k, "value": str(v)} for k, v in inputs.items()]}


def plan(intent, domain, steps, strategy=""):
  return {"intent": intent, "domain": domain, "steps": steps, "answer_strategy": strategy}


async def run(name, question, the_plan, answers, verdicts, session=None, user="srini"):
  llm = ScriptedLlm(plan=the_plan, critic_script=verdicts)
  answers = list(answers)
  original = llm.generate_content_async

  async def scripted(llm_request, stream=False):
    from fakes import _sys
    if "You are the SYNTHESIZER" in _sys(llm_request):
      llm.calls.append(("synthesizer", ""))
      text = answers.pop(0) if len(answers) > 1 else answers[0]
      from google.adk.models.llm_response import LlmResponse
      yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))
      return
    async for r in original(llm_request, stream):
      yield r
  object.__setattr__(llm, "generate_content_async", scripted)

  wf = build_workflow(model=llm, planner_model=llm, critic_model=llm, with_tools=False)
  runner = Runner(app=App(name="procedural_agent", root_agent=wf, plugins=build_plugins()),
                  session_service=SESSIONS, memory_service=MEMORY, artifact_service=ARTIFACTS,
                  auto_create_session=True)
  sid = session or name
  trace, final = [], None
  async for ev in runner.run_async(user_id=user, session_id=sid,
                                   new_message=types.Content(role="user", parts=[types.Part(text=question)])):
    node = (ev.node_info.path.split("/")[-1].split("@")[0] if getattr(ev, "node_info", None) and ev.node_info.path else ev.author)
    if not trace or trace[-1] != node:
      trace.append(node)
    if ev.author == "procedural_agent" and ev.content and ev.content.parts and ev.content.parts[0].text:
      final = ev.content.parts[0].text
  s = await SESSIONS.get_session(app_name="procedural_agent", user_id=user, session_id=sid)
  roles = [r for r, _ in llm.calls]
  return {"question": question, "final": final, "state": s.state, "roles": roles, "trace": trace,
          "planner_prompt": next((t for r, t in llm.calls if r == "planner"), "")}


def results_table(state) -> str:
  compiled, results = state["temp:compiled"] if "temp:compiled" in state else None, None
  return compiled


def write(name: str, text: str) -> None:
  OUT.mkdir(parents=True, exist_ok=True)
  (OUT / f"{name}.md").write_text(text.rstrip() + "\n")


def jblock(obj) -> str:
  return "```json\n" + json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n```"


def levels_md(compiled: dict) -> str:
  rows = ["| Level | Steps (run in parallel) | Added by the compiler |", "|---|---|---|"]
  for i, lv in enumerate(compiled["levels"]):
    added = [s for s in lv if s in compiled["added"]]
    rows.append(f"| {i} | {', '.join(f'`{s}` → `{compiled['steps'][s]['procedure']}`' for s in lv)} | "
                f"{', '.join(f'`{a}`' for a in added) or '—'} |")
  return "\n".join(rows)


def results_md(results: dict) -> str:
  rows = ["| Step | Procedure | Status | Latency | Outputs / error |", "|---|---|---|---|---|"]
  for r in results.values():
    out = json.dumps(executor.compact(r["outputs"], 3, 80), ensure_ascii=False, default=str) if r["ok"] else r["error"]
    if len(out) > 160:
      out = out[:157] + "…"
    rows.append(f"| `{r['id']}` | `{r['procedure']}` | **{r['status']}** | {r['latency_ms']:.0f} ms | `{out}` |")
  return "\n".join(rows)


def section(planner_prompt: str, title: str) -> str:
  for block in planner_prompt.split("\n\n"):
    if block.startswith(title):
      return block
  return ""


# State captured inside a turn lives under temp: keys, which ADK clears after the
# invocation; the nodes copy what the docs need into these hooks.
CAPTURE: dict = {}
from procedural_agent.harness import nodes as _nodes  # noqa: E402

_orig_execute, _orig_compile, _orig_learn = _nodes.execute_plan, _nodes.compile_plan, _nodes.learn


async def _execute(ctx, node_input):
  out = await _orig_execute(ctx, node_input)
  CAPTURE["results"] = ctx.state["temp:results"]
  return out


def _compile(ctx, node_input):
  out = _orig_compile(ctx, node_input)
  CAPTURE.setdefault("compiled_all", []).append(out)
  CAPTURE["compiled"] = out
  return out


async def _learn(ctx, node_input):
  await _orig_learn(ctx, node_input)
  CAPTURE["verdicts"] = ctx.state.get("temp:verdicts")
  CAPTURE["learning"] = ctx.state.get("last_learning")


def patch_nodes():
  # build_workflow references nodes.* at build time, so patch before building.
  _nodes.execute_plan = _execute
  _nodes.compile_plan = _compile
  _nodes.learn = _learn
  _execute.__name__, _compile.__name__, _learn.__name__ = "execute_plan", "compile_plan", "learn"


def turn_md(r: dict, extra_sections: tuple[str, ...] = ()) -> str:
  c = CAPTURE
  parts = [f"**Question:** {r['question']}", "",
           f"**Node path:** {' → '.join(f'`{n}`' for n in r['trace'] if n not in ('procedural_agent',))}", ""]
  for title in extra_sections:
    block = section(r["planner_prompt"], title)
    if block:
      parts += [f"??? note \"What the planner was given: {title.rstrip(':').split(' (')[0].title()}\"",
                "    ```text", *("    " + ln for ln in block.splitlines()), "    ```", ""]
  parts += ["**Plan from the planner (after glossary normalisation):**", "",
            jblock({k: v for k, v in c["compiled"].items() if k in ("intent", "normalized", "warnings")}), "",
            "**Compiled execution levels:**", "", levels_md(c["compiled"]), "",
            "**Step results:**", "", results_md(c["results"]), "",
            "**Critic verdicts:** " + ", ".join(f"`ok={v.get('ok')}, score={v.get('score')}`" for v in c["verdicts"]), "",
            "**Final answer:**", "", "> " + (r["final"] or "").replace("\n", "\n> "), "",
            "**What the agent learned this turn:**", "", jblock(c.get("learning") or {})]
  return "\n".join(parts)


# ---------------------------------------------------------------- scenarios
async def main():
  patch_nodes()
  OK = {"ok": True, "score": 0.92, "issues": [], "missing_data": False}
  mem = agent_memory()

  # 1. single procedure + automatic dependency
  CAPTURE.clear()
  r = await run("ex_single", "What's the weather in Hyderabad right now?",
                plan("current weather in a city", "weather", [step("s1", "get_weather_forecast", city="Hyderabad")],
                     "temperature, humidity, wind, today's range"),
                ["It's 29.4 °C in Hyderabad right now (14:15 IST, 20 Nov 2026), humidity 41%, wind 9.7 km/h, "
                 "no rain. Today: 19.8–31.2 °C, 5% chance of rain."], [OK])
  write("ex_single", turn_md(r, ("CANDIDATE PROCEDURES",)))

  # 2. dependent chain + glossary normalisation
  CAPTURE.clear()
  r = await run("ex_dependent", "Convert 250 euros to rupees",
                plan("currency conversion", "finance",
                     [step("s1", "convert_amount", amount=250, from_currency="euros", to_currency="rupees")]),
                ["250 EUR = ₹24,355.00 at 97.42 INR per EUR (ECB reference rate dated 20 Nov 2026)."], [OK])
  write("ex_dependent", turn_md(r, ("GLOSSARY",)))

  # 3. independent needs in parallel
  CAPTURE.clear()
  r = await run("ex_parallel", "What's the air quality in Delhi, and the bitcoin price in INR?",
                plan("air quality and crypto price", "mixed",
                     [step("s1", "get_air_quality", city="Delhi"),
                      step("s2", "get_crypto_price", coin="Bitcoin", vs_currency="INR")]),
                ["Delhi's air is **very unhealthy**: US AQI 212 (PM2.5 141 µg/m³) at 14:00 IST. "
                 "Bitcoin is ₹78,54,210 (CoinGecko spot)."], [OK])
  write("ex_parallel", turn_md(r, ("GLOSSARY",)))

  # 4. composite procedure + concept + city alias
  CAPTURE.clear()
  r = await run("ex_composite", "Is today a good day to go for a run in Bangalore?",
                plan("outdoor run suitability", "weather",
                     [step("s1", "city_conditions_brief", city="Bangalore")], "go / no-go with reasons"),
                ["Yes. Bengaluru is 23.6 °C with a light breeze (11.2 km/h), 20% chance of rain, and AQI 54 "
                 "(moderate, fine for most people). Go early evening for cooler air."], [OK])
  write("ex_composite", turn_md(r, ("GLOSSARY", "CANDIDATE PROCEDURES")))

  # 5. critic rejects -> revise -> Reflexion lesson
  CAPTURE.clear()
  r = await run("ex_revise", "How hot is it in Delhi?",
                plan("current temperature", "weather", [step("s1", "get_weather_forecast", city="Delhi")]),
                ["It's 24.1 degrees in Delhi.",
                 "It's 24.1 °C in Delhi right now (14:15 IST, 20 Nov 2026); today's high is 26.5 °C."],
                [{"ok": False, "score": 0.55, "issues": ["No units or timestamp on the temperature"], "missing_data": False},
                 OK])
  write("ex_revise", turn_md(r) + "\n\n**Lesson now in reflective memory:**\n\n" +
        jblock(mem.reflections.relevant("How hot is it in Delhi temperature")))

  # 6. critic says data missing -> replan
  CAPTURE.clear()
  first = plan("conditions in a city", "weather", [step("s1", "get_weather_forecast", city="Kathmandu")])
  r = await run("ex_replan", "What's the weather in Kathmandu and is the air safe?", first,
                ["Kathmandu is 15.2 °C (14:15 NPT). Air: US AQI 156, unhealthy; sensitive groups should limit "
                 "time outdoors."],
                [{"ok": False, "score": 0.3, "issues": ["Air quality was asked but not fetched"], "missing_data": True}, OK])
  write("ex_replan", turn_md(r) + "\n\nThe planner's second call received the critic's feedback:\n\n```text\n" +
        "REVIEW FEEDBACK (fix the plan):\n- Air quality was asked but not fetched\n```")

  # 7. a source is down: dependents skipped, independent branch still answers
  CAPTURE.clear()
  DOWN.add("geocoding-api.open-meteo.com")
  r = await run("ex_failure", "Weather in Hyderabad and 100 USD in INR?",
                plan("weather and conversion", "mixed",
                     [step("s1", "get_weather_forecast", city="Hyderabad"),
                      step("s2", "convert_amount", amount=100, from_currency="USD", to_currency="INR")]),
                ["100 USD = ₹8,436.00 at 84.36 (ECB, 20 Nov 2026). I couldn't get the weather: the geocoding "
                 "service returned 503, so the forecast step was skipped."], [OK])
  DOWN.clear()
  write("ex_failure", turn_md(r) + "\n\n**Reliability learned for the failing source:**\n\n" + jblock(
      [dict(r_) for r_ in mem.store.query(
          "SELECT name, success, failure FROM sources WHERE name='open_meteo_geocoding'")]))

  # 8. learning across turns: induction -> reuse -> promotion, plus plan cache
  q = "Weather and air quality in Hyderabad, and 100 USD in INR?"
  multi = plan("weather air quality and currency conversion", "travel",
               [step("s1", "get_weather_forecast", city="Hyderabad"), step("s2", "get_air_quality", city="Hyderabad"),
                step("s3", "convert_amount", amount=100, from_currency="USD", to_currency="INR")])
  CAPTURE.clear()
  r = await run("ex_learn_1", q, multi, ["Hyderabad 29.4 °C, AQI 78 (moderate). 100 USD = ₹8,436.00."], [OK])
  induced = CAPTURE["learning"]["induced"]
  p = mem.kg.get(induced)
  lines = ["### Turn 1: a successful multi-procedure run is induced as a new procedure", "",
           turn_md(r), "", "New node in the graph:", "",
           jblock(p.card() | {"composed_of": mem.kg.parts(induced), "steps_md": p.steps_md})]
  for i in range(2, 5):
    CAPTURE.clear()
    reuse = plan("same request", "travel", [step("s1", induced, city="Hyderabad", amount=100,
                                                 from_currency="USD", to_currency="INR")])
    r = await run(f"ex_learn_{i}", q, reuse, ["Hyderabad 29.4 °C, AQI 78 (moderate). 100 USD = ₹8,436.00."], [OK])
    p = mem.kg.get(induced)
    cached = section(r["planner_prompt"], "CACHED PLAN")
    lines += ["", f"### Turn {i}: the planner reuses `{induced}`", "",
              f"- Planner prompt contained a cached plan: `{cached.splitlines()[1][:140] if cached else 'none'}…`",
              f"- Compiled levels: {' → '.join('[' + ', '.join(lv) + ']' for lv in CAPTURE['compiled']['levels'])}",
              f"- `{induced}` now: status **{p.status}**, successes {p.success}, failures {p.failure}, "
              f"reliability {p.reliability:.0%}",
              f"- Learning report: `{json.dumps(CAPTURE['learning'])}`"]
  write("ex_learning", "\n".join(lines))

  # 9. ingestion of procedure cards
  ing = Ingestor(mem)

  def uv(req):
    if req.url.host == "api.open-meteo.com" and "uv_index_max" in str(req.url):
      return httpx.Response(200, json={"daily": {"time": ["2026-11-20"], "uv_index_max": [8.2]}})
    return api(req)
  executor.fetcher.transport = httpx.MockTransport(uv)
  report = await ing.stage((ROOT / "examples" / "sop_travel_cards.md").read_text(), "sop_travel_cards.md")
  applied = ing.apply(report["batch_id"], approve=["travel_budget_in_inr->get_fx_rate"])
  compiled = mem.kg.compile({"steps": [step("b", "beach_day_check", city="Bengaluru")]})
  results = await executor.run_plan(mem.kg, compiled)
  write("ex_ingest", "\n".join([
      "**Review report** (`python scripts/ingest.py examples/sop_travel_cards.md`):", "",
      "```text", render_report(report), "```", "",
      "**Apply** (`--apply-batch " + report["batch_id"] + " --approve \"travel_budget_in_inr->get_fx_rate\"`):", "",
      jblock(applied), "",
      "**The new composite runs straight away** — `beach_day_check` for Bengaluru:", "",
      levels_md(compiled), "", results_md(results)]))
  executor.fetcher.transport = httpx.MockTransport(api)

  # 10. graph diagram after everything above
  write("graph_after", "```mermaid\n" + mem.kg.to_mermaid() + "\n```")
  write("kg_stats", jblock(mem.kg.stats()))

  # 11. provider resolution (no network)
  from procedural_agent import llm
  env = {"AZURE_API_KEY": "…", "AZURE_API_BASE": "https://contoso.openai.azure.com", "AZURE_API_VERSION": "2024-10-21",
         "TFY_BASE_URL": "https://acme.truefoundry.cloud", "TFY_API_KEY": "…", "OPENAI_API_KEY": "…"}
  os.environ.update(env)
  rows = ["| Role | Spec | Provider | LiteLLM model | Reasoning | Extra call parameters |", "|---|---|---|---|---|---|"]
  for role, spec, reasoning in [("planner", "truefoundry/openai-main/gpt-5", "auto"),
                                ("synthesizer", "azure/gpt-4o-prod|truefoundry/azure-openai-main/gpt-4o|gemini-3.5-flash", "auto"),
                                ("critic", "anthropic/claude-sonnet-4-5", "low"),
                                ("learner", "openai/gpt-4.1-mini", "off"),
                                ("summarizer", "gemini-3.5-flash", "auto")]:
    for i, s in enumerate(llm.parse_chain(spec)):
      kw = llm.provider_kwargs(s, role, reasoning)
      level = llm.resolve_reasoning(s, reasoning)
      rows.append(f"| {role if i == 0 else '↳ fallback'} | `{s.raw}` | {s.provider} | `{s.litellm_model}` | "
                  f"{level or ('thinking via BuiltInPlanner' if s.is_gemini and reasoning != 'off' else 'off')} | "
                  f"`{json.dumps({k: v for k, v in kw.items() if k != 'reasoning_effort'}) if kw else '—'}` |")
  write("ex_providers", "\n".join(rows))
  for k in env:
    os.environ.pop(k, None)

  print(f"Wrote {len(list(OUT.glob('*.md')))} snippets to {OUT}")
  shutil.rmtree(DATA, ignore_errors=True)


if __name__ == "__main__":
  asyncio.run(main())
