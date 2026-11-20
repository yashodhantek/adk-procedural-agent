"""Procedural-memory real-time data agent on ADK 2.x.

`root_agent` is an ADK 2.x graph Workflow and `app` wraps it with the harness:
plugins, event compaction, context caching and resumability. Run it with
`adk web` / `adk run`, or `python scripts/run_cli.py` for persistent memory.
"""

from __future__ import annotations

from google.adk import Agent, Workflow
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.apps import App, ResumabilityConfig
from google.adk.apps._configs import EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.planners import BuiltInPlanner, PlanReActPlanner
from google.adk.workflow import RetryConfig
from google.genai import types

from . import prompts
from . import llm
from .config import settings
from .harness import nodes
from .harness.plugins import build_plugins
from .harness.tools import synthesizer_tools
from .schemas import Plan, Verdict


def _dynamic_instruction(name: str):
  """Per-call part of a prompt: learned playbook bullets, lessons and preferences.

  The fixed part goes in `static_instruction` (a stable, cacheable system prefix);
  with static_instruction set, ADK sends this dynamic part as user content."""
  def provider(ctx: ReadonlyContext) -> str:
    st = ctx.state
    return prompts.render_dynamic(
        name,
        playbook=st.get("temp:playbook", ""),
        lessons=st.get("temp:lessons", ""),
        preferences=str(st.get("user:preferences", {})),
    )
  return provider


def _thinking(level: str | None) -> types.ThinkingConfig | None:
  if not level:
    return None
  return types.ThinkingConfig(include_thoughts=False, thinking_level=level.upper())


def _role(spec: str, role: str, reasoning: str):
  """(model, planner, generate_content_config, resolved level) for one role."""
  primary = llm.parse_chain(spec)[0]
  level = llm.resolve_reasoning(primary, reasoning)
  model = llm.build_model(spec, role=role, reasoning=reasoning, cache_hints=settings.prompt_cache_hints)
  planner = None
  if primary.is_gemini and level:
    planner = BuiltInPlanner(thinking_config=_thinking(level))   # native Gemini thinking
  return model, planner, level


def build_agents(model=None, planner_model=None, critic_model=None, with_tools: bool = True):
  """Factory so tests (and the optimizer lab) can inject other models.

  Reasoning per role: Gemini -> BuiltInPlanner(thinking_level); OpenAI / Azure /
  TrueFoundry / Anthropic -> reasoning_effort on the LiteLLM call; a synthesizer
  model with no reasoning gets PlanReActPlanner (prompted plan -> act -> answer)."""
  p_model, p_planner, _ = _role(settings.planner_model, "planner", settings.planner_reasoning)
  s_model, s_planner, s_level = _role(settings.model, "synthesizer", settings.agent_reasoning)
  c_model, c_planner, _ = _role(settings.critic_model, "critic", settings.critic_reasoning)
  if model is None and s_planner is None and not s_level and settings.plan_react_fallback:
    s_planner = PlanReActPlanner()

  planner = Agent(
      name="planner",
      model=planner_model or p_model,
      description="Turns a question into a dependency-aware plan over the procedural graph.",
      static_instruction=prompts.split("planner")[0],
      instruction=_dynamic_instruction("planner"),
      output_schema=Plan,
      output_key="plan",
      planner=None if planner_model else p_planner,
      retry_config=RetryConfig(max_attempts=3, initial_delay=1.0),
  )
  synthesizer = Agent(
      name="synthesizer",
      model=model or s_model,
      description="Executes deferred steps with tools and writes the grounded answer.",
      static_instruction=prompts.split("synthesizer")[0],
      instruction=_dynamic_instruction("synthesizer"),
      tools=synthesizer_tools() if with_tools else [],
      planner=None if model else s_planner,
      output_key="draft",
      retry_config=RetryConfig(max_attempts=3, initial_delay=1.0),
  )
  critic = Agent(
      name="critic",
      model=critic_model or c_model,
      description="Verifies the draft against the fetched data.",
      static_instruction=prompts.split("critic")[0],
      output_schema=Verdict,
      output_key="verdict",
      planner=None if critic_model else c_planner,
      generate_content_config=types.GenerateContentConfig(temperature=0.0),
  )
  return planner, synthesizer, critic


def build_workflow(model=None, planner_model=None, critic_model=None, with_tools: bool = True) -> Workflow:
  planner, synthesizer, critic = build_agents(model, planner_model, critic_model, with_tools)
  return Workflow(
      name="procedural_agent",
      description="Plans over procedural memory, fetches real-time data in parallel, self-verifies and learns.",
      edges=[
          ("START", nodes.recall, planner, nodes.compile_plan, nodes.execute_plan,
           synthesizer, nodes.prepare_review, critic, nodes.gate),
          (nodes.gate, {"accept": nodes.respond, "revise": synthesizer, "replan": planner}),
          (nodes.respond, nodes.learn),
      ],
  )


def build_app(workflow: Workflow | None = None) -> App:
  return App(
      name="procedural_agent",
      root_agent=workflow or build_workflow(),
      plugins=build_plugins(),
      # Summarisation memory: older turns are compacted into summaries.
      events_compaction_config=EventsCompactionConfig(
          summarizer=LlmEventSummarizer(llm=llm.build_model(settings.summarizer_model, role="summarizer")),
          compaction_interval=settings.compaction_interval,
          overlap_size=settings.compaction_overlap,
          token_threshold=settings.compaction_token_threshold,
          event_retention_size=settings.compaction_keep_events,
      ),
      # Prompt/context caching of the stable prefix (instructions + tools).
      context_cache_config=ContextCacheConfig(cache_intervals=10, ttl_seconds=1800, min_tokens=2048)
      if settings.context_cache and llm.is_gemini(settings.model) else None,   # Gemini-only feature
      # Pause/resume across long-running tools and crashes.
      resumability_config=ResumabilityConfig(is_resumable=True),
  )


root_agent = build_workflow()
app = build_app(root_agent)
