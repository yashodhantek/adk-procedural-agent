"""Harness plugins: cross-cutting behaviour applied to every agent and tool.

Built-in ADK plugins used
  ReflectAndRetryToolPlugin   tool errors -> reflection prompt -> retry (self-correction)
  ReflectAndRetryModelPlugin  malformed function calls -> retry
  ContextFilterPlugin         hard cap on how many past invocations reach the model
  LoggingPlugin               structured logs (ADK_LOGGING=1)
  AutoTracingPlugin           OpenTelemetry spans for every node (ENABLE_TRACING=1)
  ToolCallIntegrityPlugin     HMAC-stamped tool calls (set TOOL_CALL_HMAC_KEY)
Custom plugins (below)
  ToolLearningPlugin          learns per-tool reliability into the knowledge graph
  BudgetGuardPlugin           per-turn LLM-call budget (runaway-loop guard)
  EpisodicMemoryPlugin        writes every finished session to long-term memory
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from google.adk.models.llm_response import LlmResponse
from google.adk.plugins import BasePlugin
from google.genai import types

from ..memory import agent_memory

log = logging.getLogger(__name__)


class ToolLearningPlugin(BasePlugin):
  """Records every tool call outcome so reliability is learned, not assumed."""

  def __init__(self):
    super().__init__(name="tool_learning")
    self._started: dict[str, float] = {}

  def _key(self, tool, tool_context) -> str:
    return f"{tool_context.invocation_id}:{tool.name}:{getattr(tool_context, 'function_call_id', '')}"

  async def before_tool_callback(self, *, tool, tool_args, tool_context):
    self._started[self._key(tool, tool_context)] = time.perf_counter()
    return None

  def _record(self, tool, tool_context, ok: bool) -> None:
    started = self._started.pop(self._key(tool, tool_context), time.perf_counter())
    kg = agent_memory().kg
    name = f"tool:{tool.name}"
    kg.upsert_source(name, "tool", "", f"ADK tool {tool.name}") if not kg.db.query(
        "SELECT 1 FROM sources WHERE name=?", (name,)) else None
    kg.record_source_outcome(name, ok, (time.perf_counter() - started) * 1000)

  async def after_tool_callback(self, *, tool, tool_args, tool_context, result):
    ok = not (isinstance(result, dict) and (result.get("ok") is False or "error" in result and result.get("error")))
    self._record(tool, tool_context, ok)
    return None

  async def on_tool_error_callback(self, *, tool, tool_args, tool_context, error):
    self._record(tool, tool_context, False)
    return None


class BudgetGuardPlugin(BasePlugin):
  """Stops a turn that exceeds its LLM-call budget instead of looping forever."""

  def __init__(self, max_llm_calls: int = int(os.environ.get("MAX_LLM_CALLS_PER_TURN", 40))):
    super().__init__(name="budget_guard")
    self.max_llm_calls = max_llm_calls
    self._calls: dict[str, int] = {}

  async def before_run_callback(self, *, invocation_context):
    self._calls[invocation_context.invocation_id] = 0
    return None

  async def before_model_callback(self, *, callback_context, llm_request):
    inv = callback_context.invocation_id
    self._calls[inv] = self._calls.get(inv, 0) + 1
    if self._calls[inv] > self.max_llm_calls:
      log.warning("LLM budget exhausted for invocation %s", inv)
      return LlmResponse(content=types.Content(role="model", parts=[types.Part(
          text="I stopped here because this request used its full reasoning budget. "
               "The partial results above are what I could verify.")]))
    return None

  async def after_run_callback(self, *, invocation_context):
    self._calls.pop(invocation_context.invocation_id, None)


class EpisodicMemoryPlugin(BasePlugin):
  """After every run, push the session to the long-term memory service."""

  def __init__(self):
    super().__init__(name="episodic_memory")

  async def after_run_callback(self, *, invocation_context):
    svc = invocation_context.memory_service
    if svc is None:
      return
    try:
      await svc.add_session_to_memory(invocation_context.session)
    except Exception as e:  # noqa: BLE001 - memory is best-effort
      log.warning("Episodic memory write failed: %s", e)


def build_plugins() -> list[Any]:
  from google.adk.plugins import (ContextFilterPlugin, LoggingPlugin, ReflectAndRetryModelPlugin,
                                  ReflectAndRetryToolPlugin)
  plugins: list[Any] = [
      ReflectAndRetryToolPlugin(max_retries=2, throw_exception_if_retry_exceeded=False),
      ReflectAndRetryModelPlugin(max_retries=2, throw_exception_if_retry_exceeded=False),
      ContextFilterPlugin(num_invocations_to_keep=int(os.environ.get("CONTEXT_KEEP_INVOCATIONS", 20))),
      ToolLearningPlugin(),
      BudgetGuardPlugin(),
      EpisodicMemoryPlugin(),
  ]
  if os.environ.get("ADK_LOGGING") == "1":
    plugins.append(LoggingPlugin())
  if os.environ.get("ENABLE_TRACING") == "1":
    from google.adk.plugins import AutoTracingPlugin
    plugins.append(AutoTracingPlugin())
  if key := os.environ.get("TOOL_CALL_HMAC_KEY"):
    from google.adk.plugins import ToolCallIntegrityPlugin
    plugins.append(ToolCallIntegrityPlugin(key.encode()))
  return plugins
