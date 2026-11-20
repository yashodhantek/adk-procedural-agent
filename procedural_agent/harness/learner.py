"""Distillers that turn finished runs into memory.

* induce_procedure -- Agent Workflow Memory / Memp: a successful multi-step run
                      becomes a reusable composite procedure (graph node)
* reflect          -- Reflexion: a revised or failed run becomes a lesson
* curate           -- ACE: propose playbook bullets from what went right/wrong

LlmDistiller uses Gemini with JSON output; HeuristicDistiller needs no model
and is the fallback whenever the LLM call fails.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from ..config import settings
from ..memory.store import tokens

log = logging.getLogger(__name__)


class InducedProcedure(BaseModel):
  name: str = Field(description="snake_case verb_noun name, max 5 words")
  description: str = Field(description="When to use this procedure, one sentence")
  domain: str
  inputs: list[str]
  outputs: list[str]
  steps_md: str = Field(description="Numbered markdown steps, generalised (no user-specific values)")


class Lesson(BaseModel):
  lesson: str = Field(description="One actionable sentence for next time")
  scope: str = Field(description="'global', a domain, or a procedure name")


class Bullet(BaseModel):
  section: str = Field(description="strategy | pitfall | formatting | source")
  bullet: str


class Bullets(BaseModel):
  bullets: list[Bullet] = Field(default_factory=list)


def _snake(text: str, limit: int = 5) -> str:
  return "_".join(tokens(text)[:limit]) or "learned_flow"


class HeuristicDistiller:

  async def induce_procedure(self, query: str, compiled: dict, results: dict, answer: str) -> dict:
    roots = [s["procedure"] for s in compiled["steps"].values()
             if s["procedure"] != "adhoc" and not s["id"].startswith("auto_")]
    inputs = sorted({k for s in compiled["steps"].values() for k in s.get("inputs", {})})
    outputs = sorted({k for r in results.values() if r.get("ok") for k in r.get("outputs", {})})
    intent = compiled.get("intent") or query
    steps = "\n".join(f"{i + 1}. Run `{p}`." for i, p in enumerate(roots))
    return InducedProcedure(
        name=f"{_snake(intent, 4)}_flow", domain=compiled.get("domain", "general"),
        description=f"Learned workflow for requests like: {intent}. Combines {', '.join(roots)}.",
        inputs=inputs, outputs=outputs[:12],
        steps_md=steps + "\n" + f"{len(roots) + 1}. Combine the results: {compiled.get('answer_strategy') or 'summarise'}.",
    ).model_dump()

  async def reflect(self, query: str, verdicts: list[dict], draft: str, results: dict) -> dict:
    issues = [i for v in verdicts for i in v.get("issues", [])]
    failed = [f"{r['procedure']}: {r['error']}" for r in results.values() if r.get("status") == "failed"]
    if failed:
      return Lesson(lesson=f"Source failures seen ({'; '.join(failed)[:200]}); have a fallback source "
                    "or say clearly which data is unavailable.", scope="global").model_dump()
    text = issues[0] if issues else "answer needed revision"
    return Lesson(lesson=f"For questions like '{query[:60]}': {text}", scope="global").model_dump()

  async def curate(self, query: str, verdicts: list[dict], playbook: list[dict]) -> list[dict]:
    return []


class LlmDistiller(HeuristicDistiller):

  def __init__(self, model: str | None = None):
    from .. import llm
    self.model = model or settings.learner_model
    llm.parse_chain(self.model)   # fail fast on a bad spec / missing endpoint settings

  async def _json(self, prompt: str, schema: type[BaseModel]) -> dict:
    from .. import llm
    return await llm.complete_json(self.model, prompt, schema)

  async def induce_procedure(self, query, compiled, results, answer):
    try:
      return await self._json(
          "You maintain an agent's procedural memory. Generalise this successful run into a "
          "reusable procedure (no user-specific literal values; inputs are parameter names).\n"
          f"QUESTION: {query}\nPLAN: {json.dumps(compiled['steps'])[:4000]}\n"
          f"OUTPUT KEYS: {[list(r.get('outputs', {})) for r in results.values()]}\nANSWER: {answer[:1500]}",
          InducedProcedure)
    except Exception as e:  # noqa: BLE001
      log.warning("LLM induction failed, using heuristic: %s", e)
      return await super().induce_procedure(query, compiled, results, answer)

  async def reflect(self, query, verdicts, draft, results):
    try:
      return await self._json(
          "Write one Reflexion-style lesson: what to do differently next time so the first draft "
          "passes review. Be concrete and general.\n"
          f"QUESTION: {query}\nREVIEWS: {json.dumps(verdicts)[:3000]}\n"
          f"STEP RESULTS: {json.dumps({k: {'status': v['status'], 'error': v['error']} for k, v in results.items()})[:2000]}\n"
          f"FINAL DRAFT: {draft[:1500]}", Lesson)
    except Exception as e:  # noqa: BLE001
      log.warning("LLM reflection failed, using heuristic: %s", e)
      return await super().reflect(query, verdicts, draft, results)

  async def curate(self, query, verdicts, playbook):
    try:
      out = await self._json(
          "You curate an agent playbook (ACE). Propose at most 2 NEW bullets that would have "
          "prevented the reviewer's issues, or none if existing bullets cover them. No duplicates.\n"
          f"CURRENT PLAYBOOK:\n{json.dumps([b['bullet'] for b in playbook])}\n"
          f"QUESTION: {query}\nREVIEWS: {json.dumps(verdicts)[:3000]}", Bullets)
      return out["bullets"][:2]
    except Exception as e:  # noqa: BLE001
      log.warning("LLM curation failed: %s", e)
      return []


def make_distiller() -> HeuristicDistiller:
  if settings.learner_mode == "llm":
    try:
      return LlmDistiller()
    except Exception as e:  # noqa: BLE001 - no credentials etc.
      log.warning("Falling back to heuristic distiller: %s", e)
  return HeuristicDistiller()


def safe_name(name: str) -> str:
  name = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")
  return re.sub(r"_+", "_", name)[:60] or "learned_flow"


def as_list(value: Any) -> list:
  return value if isinstance(value, list) else []
