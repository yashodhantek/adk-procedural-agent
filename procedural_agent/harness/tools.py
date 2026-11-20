"""Tools the synthesizer agent can call, plus the ADK built-in tool wiring."""

from __future__ import annotations

import json
import logging
from typing import Any

from google.adk.tools import ToolContext, load_memory
from google.adk.tools.load_web_page import load_web_page
from google.adk.tools.skill_toolset import SkillToolset
from google.genai import types

from ..config import settings
from ..memory import KGSkillRegistry, Procedure, agent_memory
from .executor import compact, fetcher, run_plan

log = logging.getLogger(__name__)


# ---------------------------------------------------------- procedural memory
def find_procedures(query: str) -> dict:
  """Search procedural memory for procedures relevant to a goal.

  Args:
    query: The goal in plain words, e.g. "weather and air quality in a city".
  """
  kg = agent_memory().kg
  return {"procedures": [p.card() | {"depends_on": kg.dependencies(p.name)} for p in kg.search(query)]}


async def run_procedure(name: str, inputs_json: str, tool_context: ToolContext) -> dict:
  """Run one procedure from procedural memory, including everything it depends on.

  Args:
    name: Exact procedure name (see find_procedures).
    inputs_json: JSON object of inputs, e.g. {"city": "Pune"}.
  """
  kg = agent_memory().kg
  try:
    inputs = json.loads(inputs_json or "{}")
    compiled = kg.compile({"steps": [{"id": "main", "procedure": name,
                                      "inputs": [{"name": k, "value": str(v)} for k, v in inputs.items()]}]})
  except (ValueError, json.JSONDecodeError) as e:
    return {"ok": False, "error": str(e)}
  results = await run_plan(kg, compiled)
  tool_context.state["temp:last_procedure_results"] = results
  main = results.get("main", {})
  return {"ok": main.get("ok", False), "outputs": compact(main.get("outputs", {})),
          "error": main.get("error"),
          "upstream": {k: v["status"] for k, v in results.items() if k != "main"}}


def teach_procedure(name: str, description: str, steps_md: str, inputs: list[str],
                    outputs: list[str], depends_on: list[str], tool_context: ToolContext) -> dict:
  """Save a new procedure the user explicitly teaches (written steps, not executable).

  Args:
    name: snake_case name.
    description: When to use it.
    steps_md: Numbered markdown steps.
    inputs: Input parameter names.
    outputs: Output names.
    depends_on: Names of existing procedures it needs first.
  """
  kg = agent_memory().kg
  from .learner import safe_name
  pname = safe_name(name)
  kg.upsert_procedure(Procedure(name=pname, description=description, steps_md=steps_md,
                                inputs=inputs, outputs=outputs, origin="user", status="active"))
  linked, rejected = [], []
  for dep in depends_on:
    try:
      if kg.get(dep):
        kg.add_edge(pname, dep, "DEPENDS_ON")
        linked.append(dep)
      else:
        rejected.append(dep)
    except ValueError:
      rejected.append(dep)
  return {"saved": pname, "linked": linked, "unknown_or_cyclic": rejected}


# ---------------------------------------------------------- semantic memory
def remember_fact(subject: str, fact: str, kind: str, tool_context: ToolContext) -> dict:
  """Store a durable fact or preference the user stated (not something you inferred).

  Args:
    subject: Short key, e.g. "home_city", "preferred_currency".
    fact: The fact in one sentence.
    kind: "preference", "fact" or "domain".
  """
  uid = tool_context.user_id
  fid = agent_memory().facts.remember(uid, subject, fact, kind if kind in ("preference", "fact", "domain") else "fact")
  if kind == "preference":   # mirror into user-scoped state: visible in every session
    prefs = dict(tool_context.state.get("user:preferences", {}))
    prefs[subject] = fact
    tool_context.state["user:preferences"] = prefs
  return {"stored": fid}


def recall_facts(query: str, tool_context: ToolContext) -> dict:
  """Look up stored facts and preferences about the user or domain.

  Args:
    query: What you need to know.
  """
  return {"facts": agent_memory().facts.search(tool_context.user_id, query)}


def forget_fact(fact_id: int, tool_context: ToolContext) -> dict:
  """Delete a stored fact when the user asks you to forget it.

  Args:
    fact_id: Id returned by recall_facts.
  """
  return {"deleted": agent_memory().facts.forget(tool_context.user_id, fact_id)}


# ---------------------------------------------------------- real-time data
async def http_get_json(url: str, params_json: str, tool_context: ToolContext) -> dict:
  """GET a JSON API on an allow-listed host (for data no procedure covers yet).

  Args:
    url: Full https URL.
    params_json: JSON object of query parameters, or "{}".
  """
  try:
    data = await fetcher.get_json(url, json.loads(params_json or "{}"))
  except Exception as e:  # noqa: BLE001
    return {"ok": False, "error": str(e)}
  raw = json.dumps(data)
  artifact = None
  if len(raw) > 4000:  # artifact memory: keep the full payload out of the prompt
    artifact = f"http_{abs(hash(url)) % 10**8}.json"
    await tool_context.save_artifact(artifact, types.Part.from_bytes(data=raw.encode(), mime_type="application/json"))
  return {"ok": True, "data": compact(data), "full_payload_artifact": artifact}


# ---------------------------------------------------------- tool assembly
def skill_toolset() -> SkillToolset:
  mem = agent_memory()
  return SkillToolset(registry=KGSkillRegistry(mem.kg, mem.reflections))


def mcp_toolsets() -> list[Any]:
  sets = []
  for server in settings.mcp_servers:
    try:
      from google.adk.tools.mcp_tool import McpToolset, StreamableHTTPConnectionParams
      sets.append(McpToolset(
          connection_params=StreamableHTTPConnectionParams(url=server["url"], headers=server.get("headers", {})),
          tool_name_prefix=server.get("name"), tool_list_cache_ttl_seconds=300))
    except Exception as e:  # noqa: BLE001
      log.warning("Skipping MCP server %s: %s", server, e)
  return sets


def synthesizer_tools() -> list[Any]:
  tools: list[Any] = [
      run_procedure, find_procedures, teach_procedure,
      remember_fact, recall_facts, forget_fact,
      define_term, lookup_term, ingest_text, apply_ingest,
      http_get_json, load_web_page,
      load_memory,             # episodic recall on demand (ADK memory service)
      skill_toolset(),         # procedures as Agent Skills (progressive disclosure)
  ]
  from .search import search_tools
  tools += search_tools()
  return tools + mcp_toolsets()


# ---------------------------------------------------------- glossary
def define_term(term: str, kind: str, definition: str, aliases: list[str], applies_to: list[str],
                related_procedures: list[str]) -> dict:
  """Add or update a glossary entry when the user defines domain vocabulary.

  Args:
    term: Canonical form (e.g. "INR", "latitude", "churn rate").
    kind: "value" (a canonical value), "parameter" (an input/output name) or "concept".
    definition: What it means, one or two sentences.
    aliases: Other ways people say it.
    applies_to: For values, the parameter names it is valid for (e.g. ["to_currency"]).
    related_procedures: Procedure names this term is about.
  """
  try:
    agent_memory().glossary.define(term, kind, definition, aliases, scope=applies_to,
                                   links=related_procedures, origin="user")
  except ValueError as e:
    return {"ok": False, "error": str(e)}
  return {"ok": True, "term": term, "kind": kind}


def lookup_term(text: str) -> dict:
  """Find glossary meanings of a word or phrase (or every term in a sentence).

  Args:
    text: A term or a sentence.
  """
  g = agent_memory().glossary
  exact = g.lookup(text)
  return {"matches": g.render([t | {"matched": text} for t in exact] or g.resolve(text, kinds=("value", "concept", "parameter")))}


# ---------------------------------------------------------- ingestion
async def ingest_text(text: str, source_name: str) -> dict:
  """Turn pasted SOP / runbook text into staged procedures, edges and glossary terms.

  Nothing is saved until apply_ingest. Show the user the review summary first.

  Args:
    text: The document text (free-form, or procedure cards).
    source_name: Where it came from, e.g. "travel SOP v3".
  """
  from .ingest import Ingestor, render_report
  try:
    report = await Ingestor(agent_memory()).stage(text, source_name)
  except Exception as e:  # noqa: BLE001
    return {"ok": False, "error": str(e)}
  return {"ok": True, "batch_id": report["batch_id"], "review": render_report(report),
          "edges_needing_confirmation": [f"{e['src']}->{e['dst']}" for e in report["edges"] if e["status"] == "review"]}


def apply_ingest(batch_id: str, approve_edges: list[str]) -> dict:
  """Save a staged ingestion batch after the user has reviewed it.

  Args:
    batch_id: From ingest_text.
    approve_edges: Review edges the user confirmed, as "src->dst"; ["all"] approves every one.
  """
  from .ingest import Ingestor
  try:
    return {"ok": True, **Ingestor(agent_memory()).apply(batch_id, "all" if approve_edges == ["all"] else approve_edges)}
  except (KeyError, ValueError) as e:
    return {"ok": False, "error": str(e)}
