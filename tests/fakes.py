"""Offline test doubles: a scripted LLM and mock HTTP APIs (no keys, no network)."""

from __future__ import annotations

import json
from typing import AsyncGenerator

import httpx
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types


def _sys(req) -> str:
  si = req.config.system_instruction if req.config else None
  if isinstance(si, types.Content):
    return " ".join(p.text or "" for p in si.parts)
  return str(si or "")


class ScriptedLlm(BaseLlm):
  """Plays planner / synthesizer / critic roles from a script.

  critic_script: list of verdict dicts returned in order (last one repeats).
  """
  model: str = "scripted"
  plan: dict = {}
  critic_script: list = []
  synth_tool_call: dict | None = None
  calls: list = []

  async def generate_content_async(self, llm_request, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
    sys = _sys(llm_request)
    last = llm_request.contents[-1] if llm_request.contents else None
    last_text = " ".join(p.text or "" for p in (last.parts or [])) if last else ""
    if "You are the PLANNER" in sys:
      role = "planner"
      self.calls.append((role, last_text))
      yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=json.dumps(self.plan))]))
      return
    if "You are the CRITIC" in sys:
      role = "critic"
      n = sum(1 for r, _ in self.calls if r == "critic")
      self.calls.append((role, last_text))
      verdict = self.critic_script[min(n, len(self.critic_script) - 1)]
      yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=json.dumps(verdict))]))
      return
    # synthesizer
    self.calls.append(("synthesizer", last_text))
    has_fn_response = any(p.function_response for c in llm_request.contents for p in (c.parts or []))
    if self.synth_tool_call and not has_fn_response:
      yield LlmResponse(content=types.Content(role="model", parts=[types.Part(
          function_call=types.FunctionCall(name=self.synth_tool_call["name"], args=self.synth_tool_call["args"]))]))
      return
    revision = any("REVIEW FEEDBACK" in (pt.text or "") for c in llm_request.contents for pt in (c.parts or []))
    text = ("Revised: " if revision else "") + "Hyderabad is 29.5 °C now (2026-11-20 14:00 local); AQI 62 (moderate). " \
           "100 USD = 8400.0 INR at 84.0 (rate date 2026-11-20)."
    yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))


def mock_transport(fail_hosts: tuple[str, ...] = ()) -> httpx.MockTransport:
  def handler(request: httpx.Request) -> httpx.Response:
    host, path, q = request.url.host, request.url.path, dict(request.url.params)
    if host in fail_hosts:
      return httpx.Response(503, json={"error": "down"})
    if host == "geocoding-api.open-meteo.com":
      return httpx.Response(200, json={"results": [{"name": q.get("name"), "latitude": 17.38, "longitude": 78.46,
                                                    "country": "India", "timezone": "Asia/Kolkata"}]})
    if host == "api.open-meteo.com":
      assert q["latitude"] == "17.38", q
      return httpx.Response(200, json={"current": {"time": "2026-11-20T14:00", "temperature_2m": 29.5,
                                                   "relative_humidity_2m": 40, "wind_speed_10m": 9.0, "precipitation": 0},
                                       "daily": {"time": ["2026-11-20"], "temperature_2m_max": [31]}})
    if host == "air-quality-api.open-meteo.com":
      return httpx.Response(200, json={"current": {"us_aqi": 62, "pm2_5": 18.1, "pm10": 40.2}})
    if host == "api.frankfurter.app":
      return httpx.Response(200, json={"amount": 1.0, "base": q["from"], "date": "2026-11-20", "rates": {q["to"]: 84.0}})
    return httpx.Response(404, json={})
  return httpx.MockTransport(handler)
