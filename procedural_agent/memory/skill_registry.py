"""Expose the procedural knowledge graph to ADK's SkillToolset.

Every active procedure becomes an Agent Skill (progressive disclosure):
  L1  name + description               -> search_skills / list results
  L2  steps, I/O, dependencies, stats  -> load_skill
  L3  call spec + learned lessons      -> load_skill_resource
So procedures the agent *learns* show up as skills with no redeploy.
"""

from __future__ import annotations

import json

from google.adk.skills import Frontmatter, Resources, Skill, SkillRegistry

from .procedural_kg import ProceduralKG
from .reflection import ReflectionMemory


def to_skill_name(proc_name: str) -> str:
  return proc_name.replace("_", "-")


def to_proc_name(skill_name: str) -> str:
  return skill_name.replace("-", "_")


class KGSkillRegistry(SkillRegistry):

  def __init__(self, kg: ProceduralKG, reflections: ReflectionMemory | None = None, k: int = 6):
    self.kg = kg
    self.reflections = reflections
    self.k = k

  def search_tool_description(self) -> str | None:
    return ("Search the procedural memory graph for how-to procedures (data retrieval "
            "recipes, learned workflows). Query with the user's goal in plain words.")

  async def search_skills(self, *, query: str) -> list[Frontmatter]:
    return [Frontmatter(name=to_skill_name(p.name), description=p.description[:1000],
                        metadata={"domain": p.domain, "reliability": round(p.reliability, 2),
                                  "status": p.status, "origin": p.origin})
            for p in self.kg.search(query, k=self.k)]

  async def get_skill(self, *, name: str) -> Skill:
    p = self.kg.get(to_proc_name(name))
    if p is None or p.status == "deprecated":
      raise KeyError(f"No active procedure named {name}")
    deps = self.kg.dependencies(p.name)
    parts = self.kg.parts(p.name)
    body = [
        f"# {p.name} (v{p.version}, {p.origin}, reliability {p.reliability:.0%})",
        p.description, "",
        f"**Inputs:** {', '.join(p.inputs) or '-'}  ",
        f"**Outputs:** {', '.join(p.outputs) or '-'}  ",
        f"**Depends on:** {', '.join(deps) or 'nothing'}  ",
    ]
    if parts:
      body.append(f"**Composed of:** {', '.join(parts)}  ")
    body += ["", "## Steps", p.steps_md or "(no written steps)", "",
             "If the procedure is executable, prefer the `run_procedure` tool over manual calls."]
    references = {}
    if p.call:
      references["call_spec.json"] = json.dumps(p.call, indent=2)
    if self.reflections:
      lessons = self.reflections.relevant(f"{p.name} {p.description}", k=5)
      if lessons:
        references["lessons.md"] = "\n".join(f"- {l['lesson']}" for l in lessons)
    return Skill(
        frontmatter=Frontmatter(name=to_skill_name(p.name), description=p.description[:1000]),
        instructions="\n".join(body),
        resources=Resources(references=references),
    )
