"""Deterministic workflow nodes (ADK 2.x FunctionNodes) around the LLM agents.

    recall -> planner* -> compile_plan -> execute_plan -> synthesizer* -> prepare_review
           -> critic* -> gate --accept--> respond -> learn
                           |--revise--> synthesizer
                           '--replan--> planner                (* = LLM agent)
"""

from __future__ import annotations

import json
import logging

from google.adk import Context
from google.genai import types

from ..config import settings
from ..memory import Procedure, agent_memory
from .executor import compact, run_plan
from .learner import make_distiller, safe_name

log = logging.getLogger(__name__)
_distiller = None


def distiller():
  global _distiller
  if _distiller is None:
    _distiller = make_distiller()
  return _distiller


def _text(value) -> str:
  if isinstance(value, types.Content):
    return "".join(p.text or "" for p in value.parts or [])
  return value if isinstance(value, str) else json.dumps(value, default=str)


def _planner_prompt(state, feedback: str = "") -> str:
  b = state["temp:brief"]
  parts = [
      f"QUESTION:\n{state['temp:query']}",
      f"USER FACTS AND PREFERENCES:\n{json.dumps(b['facts']) if b['facts'] else 'none'}",
      f"RELEVANT PAST EPISODES:\n{b['episodes'] or 'none'}",
      "GLOSSARY (what the user's words mean; use the canonical values):\n"
      + (json.dumps(b.get("glossary"), ensure_ascii=False) if b.get("glossary") else "none"),
      "CANDIDATE PROCEDURES (name, inputs, outputs, depends_on, reliability):\n" + json.dumps(b["procedures"], indent=1),
      f"CACHED PLAN FOR A SIMILAR QUESTION:\n{json.dumps(b['cached_plan']) if b['cached_plan'] else 'none'}",
  ]
  if feedback:
    parts.append(f"REVIEW FEEDBACK (fix the plan):\n{feedback}")
  return "\n\n".join(parts)


def _synth_prompt(state, feedback: str = "") -> str:
  compiled = state.get("temp:compiled") or {}
  results = state.get("temp:results") or {}
  parts = [
      f"QUESTION:\n{state['temp:query']}",
      f"PLAN: intent={compiled.get('intent')!r}; strategy={compiled.get('answer_strategy')!r}; "
      f"warnings={compiled.get('warnings')}",
      "STEP RESULTS:\n" + json.dumps({k: {"procedure": v["procedure"], "status": v["status"],
                                          "outputs": compact(v["outputs"]), "error": v["error"]}
                                      for k, v in results.items()}, indent=1, default=str),
  ]
  if state.get("temp:results_artifact"):
    parts.append(f"(Full raw results saved as artifact {state['temp:results_artifact']}.)")
  if feedback:
    parts.append(f"YOUR PREVIOUS DRAFT:\n{state.get('temp:draft', '')}\n\nREVIEW FEEDBACK (fix these):\n{feedback}")
  return "\n\n".join(parts)


# ------------------------------------------------------------------- nodes
async def recall(ctx: Context, node_input: str) -> str:
  """Working-memory setup + retrieval from every long-term store."""
  mem = agent_memory()
  query = _text(node_input).strip()
  st = ctx.state
  st["temp:query"] = query
  st["temp:revision"] = 0
  st["temp:replans"] = 0
  st["temp:verdicts"] = []
  st["turns"] = st.get("turns", 0) + 1          # session-scoped working memory

  episodes = ""
  try:
    found = await ctx.search_memory(query)
    snippets = []
    for m in (found.memories or [])[:4]:
      txt = " ".join(p.text or "" for p in (m.content.parts or []))
      if txt.strip():
        snippets.append(f"- [{m.timestamp or ''}] {txt[:300]}")
    episodes = "\n".join(snippets)
  except Exception as e:  # noqa: BLE001 - no memory service configured
    log.debug("episodic recall skipped: %s", e)

  terms = mem.glossary.resolve(query)
  procs = mem.kg.search(mem.glossary.expand_query(query), k=10)
  cards = [p.card() | {"depends_on": mem.kg.dependencies(p.name), "parts": mem.kg.parts(p.name)} for p in procs]
  cached = mem.kg.cached_plan(query)
  playbook = mem.reflections.playbook(settings.playbook_size)
  st["temp:playbook_ids"] = [b["id"] for b in playbook]
  st["temp:playbook"] = mem.reflections.render(playbook)
  st["temp:lessons"] = "\n".join(f"- {l['lesson']}" for l in mem.reflections.relevant(query))
  st["temp:brief"] = {"facts": mem.facts.search(ctx.user_id, query), "episodes": episodes,
                      "glossary": mem.glossary.render(terms),
                      "procedures": cards, "cached_plan": cached}
  return _planner_prompt(st)


def normalize_plan(plan: dict, glossary, kg=None) -> tuple[dict, list[str]]:
  """Canonicalise input names and values with the glossary ('rupees' -> 'INR').

  A name the procedure itself declares is never renamed."""
  notes = []
  plan = json.loads(json.dumps(plan or {}))
  for step in plan.get("steps", []):
    proc = kg.get(step.get("procedure", "")) if kg else None
    declared = set(proc.inputs) if proc else set()
    for item in step.get("inputs", []):
      name = item["name"] if item["name"] in declared else glossary.canonical_param(item["name"])
      value = glossary.normalize_value(name, item["value"])
      if (name, value) != (item["name"], item["value"]):
        notes.append(f"{step['id']}: {item['name']}={item['value']!r} -> {name}={value!r}")
      item["name"], item["value"] = name, value
  return plan, notes


def compile_plan(ctx: Context, node_input: dict) -> dict:
  mem = agent_memory()
  kg = mem.kg
  node_input, notes = normalize_plan(node_input, mem.glossary, kg)
  try:
    compiled = kg.compile(node_input or {})
    compiled["normalized"] = notes
  except ValueError as e:
    compiled = {"intent": (node_input or {}).get("intent", ""), "domain": "general", "answer_strategy": "",
                "steps": {}, "levels": [], "added": [], "warnings": [f"Plan rejected: {e}"]}
  ctx.state["temp:plan"] = node_input
  ctx.state["temp:compiled"] = compiled
  return compiled


async def execute_plan(ctx: Context, node_input: dict) -> str:
  kg = agent_memory().kg
  compiled = ctx.state["temp:compiled"]
  results = await run_plan(kg, compiled)
  ctx.state["temp:results"] = results
  try:   # artifact memory: the full payloads, versioned per session
    name = "plan_results.json"
    await ctx.save_artifact(name, types.Part.from_bytes(
        data=json.dumps({"plan": compiled, "results": results}, default=str).encode(),
        mime_type="application/json"))
    ctx.state["temp:results_artifact"] = name
  except Exception as e:  # noqa: BLE001 - no artifact service configured
    log.debug("artifact save skipped: %s", e)
  return _synth_prompt(ctx.state)


def prepare_review(ctx: Context, node_input) -> str:
  draft = _text(node_input)
  ctx.state["temp:draft"] = draft
  results = ctx.state.get("temp:results") or {}
  return "\n\n".join([
      f"QUESTION:\n{ctx.state['temp:query']}",
      "STEP RESULTS:\n" + json.dumps({k: {"status": v["status"], "outputs": compact(v["outputs"]),
                                          "error": v["error"]} for k, v in results.items()}, default=str),
      f"DRAFT:\n{draft}",
  ])


def gate(ctx: Context, node_input: dict):
  """Self-correction policy: accept, revise the answer, or re-plan the data."""
  st = ctx.state
  verdict = node_input or {}
  st["temp:verdicts"] = list(st.get("temp:verdicts", [])) + [verdict]
  issues = "\n".join(f"- {i}" for i in verdict.get("issues", [])) or "- (no details)"
  if verdict.get("ok") or float(verdict.get("score", 0)) >= settings.accept_score:
    ctx.route = "accept"
    return st["temp:draft"]
  if verdict.get("missing_data") and st["temp:replans"] < settings.max_replans:
    st["temp:replans"] += 1
    ctx.route = "replan"
    return _planner_prompt(st, issues)
  if st["temp:revision"] < settings.max_revisions:
    st["temp:revision"] += 1
    ctx.route = "revise"
    return _synth_prompt(st, issues)
  st["temp:unverified"] = True
  ctx.route = "accept"
  return st["temp:draft"]


def respond(ctx: Context, node_input) -> types.Content:
  text = _text(node_input)
  if ctx.state.get("temp:unverified"):
    text += "\n\n_Note: the reviewer could not fully verify this answer._"
  return types.Content(role="model", parts=[types.Part(text=text)])


async def learn(ctx: Context, node_input) -> None:
  """Self-learning step. Runs after the answer is delivered."""
  if not settings.learning_enabled:
    return None
  mem = agent_memory()
  st = ctx.state
  query = st["temp:query"]
  compiled = st.get("temp:compiled") or {}
  results = st.get("temp:results") or {}
  verdicts = st.get("temp:verdicts", [])
  final = verdicts[-1] if verdicts else {}
  success = bool(final.get("ok") or float(final.get("score", 0)) >= settings.accept_score)
  first_try = success and len(verdicts) == 1
  learned: dict = {}
  try:
    # 1. Plan cache (procedural memory of whole plans)
    if compiled.get("steps") and st.get("temp:plan"):
      mem.kg.cache_plan(query, st["temp:plan"], success)

    # 2. Memp-style update. Executable steps were already scored by the executor;
    #    written-steps-only procedures (deferred) are scored by the turn outcome.
    for sid, s in compiled.get("steps", {}).items():
      if (results.get(sid) or {}).get("status") == "deferred" and mem.kg.get(s["procedure"]):
        mem.kg.record_outcome(s["procedure"], success)
    for name in {s["procedure"] for s in compiled.get("steps", {}).values()}:
      p = mem.kg.get(name)
      if not p or p.origin == "seed":
        continue
      if p.status == "candidate" and p.success >= settings.promote_after:
        mem.kg.set_status(name, "active")
        learned["promoted"] = name
      elif p.success + p.failure >= 4 and p.reliability < settings.deprecate_below:
        mem.kg.set_status(name, "deprecated")
        learned["deprecated"] = name

    # 3. AWM-style induction of a new composite procedure
    roots = sorted({s["procedure"] for s in compiled.get("steps", {}).values()
                    if s["procedure"] != "adhoc" and not s["id"].startswith(("auto_",))
                    and not mem.kg.parts(s["procedure"])})
    root_steps = [sid for sid, s in compiled.get("steps", {}).items() if s["procedure"] in roots]
    all_roots_ok = all((results.get(sid) or {}).get("ok") for sid in root_steps)
    # Only a run where every chosen procedure actually worked becomes a new procedure.
    if success and all_roots_ok and len(roots) >= 2 and not _composite_exists(mem.kg, roots):
      spec = await distiller().induce_procedure(query, compiled, results, st.get("temp:draft", ""))
      name = safe_name(spec["name"])
      if mem.kg.get(name):
        name = f"{name}_{len(mem.kg.all(include_deprecated=True))}"
      mem.kg.upsert_procedure(Procedure(
          name=name, description=spec["description"], domain=spec.get("domain", "general"),
          inputs=spec.get("inputs", []), outputs=spec.get("outputs", []), steps_md=spec.get("steps_md", ""),
          call={"kind": "composite"}, status="candidate", origin="learned", success=1))
      for part in roots:
        mem.kg.add_edge(name, part, "COMPOSED_OF")
      learned["induced"] = name

    # 4. Reflexion lesson when the first draft did not pass
    if not first_try and verdicts:
      lesson = await distiller().reflect(query, verdicts, st.get("temp:draft", ""), results)
      learned["lesson"] = mem.reflections.add_lesson(query, lesson["lesson"], lesson.get("scope", "global"))

    # 5. ACE playbook: credit or blame the bullets that were in context, add new ones
    ids = st.get("temp:playbook_ids", [])
    mem.reflections.score_bullets(ids, helpful=first_try)
    if not first_try:
      for b in await distiller().curate(query, verdicts, mem.reflections.playbook(settings.playbook_size)):
        mem.reflections.add_bullet(b["bullet"], b.get("section", "strategy"))
  except Exception as e:  # noqa: BLE001 - learning must never break a turn
    log.warning("learning step failed: %s", e)
  st["last_learning"] = learned
  return None


def _composite_exists(kg, parts: list[str]) -> bool:
  target = set(parts)
  for p in kg.all(include_deprecated=False):
    if set(kg.parts(p.name)) == target:
      return True
  return False
