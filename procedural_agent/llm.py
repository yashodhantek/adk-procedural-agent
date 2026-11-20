"""Model provider layer: one place that turns a model string into a model.

Every role (AGENT_MODEL, PLANNER_MODEL, CRITIC_MODEL, LEARNER_MODEL,
SUMMARIZER_MODEL) takes a *model spec*:

  gemini-3.5-flash                      Gemini via google-genai (API key or Vertex AI)
  openai/gpt-4.1                        OpenAI            OPENAI_API_KEY [OPENAI_BASE_URL]
  azure/<deployment-name>               Azure OpenAI      AZURE_API_KEY, AZURE_API_BASE, AZURE_API_VERSION
  truefoundry/<provider-account>/<model>  TrueFoundry AI Gateway  TFY_API_KEY, TFY_GATEWAY_URL
        e.g. truefoundry/azure-openai-main/gpt-4o   (Azure OpenAI behind TrueFoundry)
             truefoundry/openai-main/gpt-4o-mini
  openai_compatible/<model>             any OpenAI-compatible endpoint  OPENAI_COMPAT_BASE_URL, OPENAI_COMPAT_API_KEY
  anthropic/..., bedrock/..., ollama_chat/..., vertex_ai/...   anything else LiteLLM supports

Join specs with "|" for an ordered fallback chain:
  AGENT_MODEL="azure/gpt-4o|truefoundry/openai-main/gpt-4o|gemini-3.5-flash"

ADK agents get a BaseLlm (Gemini, LiteLlm or FallbackLlm). Non-agent calls
(learner, ingestion extractor) use `complete_json`, which honours the same specs.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, AsyncGenerator

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from pydantic import BaseModel, PrivateAttr

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelSpec:
  raw: str
  provider: str          # gemini | openai | azure | truefoundry | openai_compatible | litellm
  litellm_model: str     # what LiteLLM is called with (unused for gemini)
  kwargs: dict

  @property
  def is_gemini(self) -> bool:
    return self.provider == "gemini"


def _env(*names: str, default: str = "") -> str:
  for n in names:
    if os.environ.get(n):
      return os.environ[n]
  return default


def _headers(var: str) -> dict:
  try:
    return json.loads(os.environ.get(var, "") or "{}")
  except json.JSONDecodeError:
    log.warning("%s is not valid JSON; ignored", var)
    return {}


def parse(spec: str) -> ModelSpec:
  spec = spec.strip()
  if spec.startswith("gemini/"):
    spec = spec.split("/", 1)[1]
  if spec.startswith("gemini-") or spec.startswith("projects/"):   # native Gemini / Vertex resource
    return ModelSpec(spec, "gemini", spec, {})

  provider, _, rest = spec.partition("/")
  if not rest:
    raise ValueError(f"Model spec '{spec}' needs a provider prefix, e.g. openai/{spec}")

  if provider == "truefoundry":
    base = _env("TFY_GATEWAY_URL")
    if not base and _env("TFY_BASE_URL"):
      base = _env("TFY_BASE_URL").rstrip("/") + "/api/llm"
    if not base:
      raise ValueError("truefoundry/* models need TFY_GATEWAY_URL (e.g. https://<org>.truefoundry.cloud/api/llm)")
    kwargs = {"api_base": base, "api_key": _env("TFY_API_KEY")}
    if headers := _headers("TFY_EXTRA_HEADERS"):   # e.g. {"X-TFY-METADATA": "{\"app\":\"agent\"}"}
      kwargs["extra_headers"] = headers
    # The gateway speaks the OpenAI API; the model id is provider_account/model.
    return ModelSpec(spec, "truefoundry", f"openai/{rest}", kwargs)

  if provider == "azure":
    kwargs = {k: v for k, v in {
        "api_key": _env("AZURE_API_KEY", "AZURE_OPENAI_API_KEY"),
        "api_base": _env("AZURE_API_BASE", "AZURE_OPENAI_ENDPOINT"),
        "api_version": _env("AZURE_API_VERSION", "OPENAI_API_VERSION", default="2024-10-21"),
    }.items() if v}
    if not kwargs.get("api_base"):
      raise ValueError("azure/* models need AZURE_API_BASE (https://<resource>.openai.azure.com)")
    return ModelSpec(spec, "azure", spec, kwargs)

  if provider == "openai":
    kwargs = {k: v for k, v in {"api_key": _env("OPENAI_API_KEY"),
                                "api_base": _env("OPENAI_BASE_URL", "OPENAI_API_BASE")}.items() if v}
    return ModelSpec(spec, "openai", spec, kwargs)

  if provider == "openai_compatible":
    base = _env("OPENAI_COMPAT_BASE_URL")
    if not base:
      raise ValueError("openai_compatible/* models need OPENAI_COMPAT_BASE_URL")
    kwargs = {"api_base": base, "api_key": _env("OPENAI_COMPAT_API_KEY", default="none")}
    if headers := _headers("OPENAI_COMPAT_HEADERS"):
      kwargs["extra_headers"] = headers
    return ModelSpec(spec, "openai_compatible", f"openai/{rest}", kwargs)

  return ModelSpec(spec, "litellm", spec, {})   # anthropic/, bedrock/, ollama_chat/, vertex_ai/ ...


def parse_chain(spec: str) -> list[ModelSpec]:
  return [parse(s) for s in spec.split("|") if s.strip()]


def is_gemini(spec: str) -> bool:
  """True when the *primary* model is native Gemini. String check only, so it
  never needs provider credentials or endpoints to be configured."""
  primary = (spec or "").split("|")[0].strip()
  return primary.startswith(("gemini-", "gemini/", "projects/"))


# ------------------------------------------------------ provider features
LEVELS = ("minimal", "low", "medium", "high")
_REASONING_NAMES = ("o1", "o3", "o4", "gpt-5", "gpt-oss", "reasoning", "thinking", "deepseek-r1",
                    "claude-opus-4", "claude-sonnet-4", "claude-3-7", "qwq", "magistral")


def base_model_name(s: ModelSpec) -> str:
  """Best guess at the vendor model name behind a spec (for capability lookups)."""
  name = s.litellm_model.split("/", 1)[-1]
  if s.provider in ("truefoundry", "openai_compatible"):
    name = name.split("/")[-1]           # provider_account/model -> model
  return name


def supports_reasoning(s: ModelSpec) -> bool:
  if s.is_gemini:
    return any(v in s.litellm_model for v in ("2.5", "-3", "thinking"))
  try:
    import litellm
    for candidate in (s.litellm_model, base_model_name(s)):
      try:
        if litellm.supports_reasoning(model=candidate):
          return True
      except Exception:  # noqa: BLE001 - unknown model name
        pass
  except ImportError:
    pass
  return any(k in base_model_name(s).lower() for k in _REASONING_NAMES)


def resolve_reasoning(s: ModelSpec, setting: str | None) -> str | None:
  """off/None -> None; auto -> 'medium' if the model reasons; explicit level -> that level."""
  setting = (setting or "off").lower()
  if setting in ("off", "none", "false", "0", ""):
    return None
  if setting == "auto":
    return "medium" if supports_reasoning(s) else None
  if setting not in LEVELS:
    raise ValueError(f"Reasoning level must be off, auto or one of {LEVELS}")
  return setting


def is_anthropic(s: ModelSpec) -> bool:
  return "claude" in s.litellm_model.lower() or s.litellm_model.startswith(("anthropic/", "bedrock/anthropic"))


def provider_kwargs(s: ModelSpec, role: str | None = None, reasoning: str | None = None,
                    cache_hints: bool = True) -> dict:
  """LiteLLM call parameters for reasoning and prompt caching (non-Gemini specs).

  * reasoning: `reasoning_effort` (OpenAI/Azure o-series & GPT-5; LiteLLM maps it to
    Anthropic extended thinking budgets)
  * caching:   OpenAI/Azure cache automatically on a stable >=1024-token prefix;
    `prompt_cache_key` improves hit rates per role. Anthropic needs explicit
    cache_control markers, injected on the system prompt.
  """
  kw: dict = {}
  if s.is_gemini:
    return kw
  level = resolve_reasoning(s, reasoning)
  if level:
    kw["reasoning_effort"] = level
  if cache_hints:
    if is_anthropic(s):
      kw["cache_control_injection_points"] = [{"location": "message", "role": "system"}]
    elif s.provider in ("openai", "azure", "truefoundry") and role:
      key = f"procedural-agent:{role}"
      if s.provider == "truefoundry":   # forwarded untouched by the OpenAI-compatible gateway
        kw["extra_body"] = {"prompt_cache_key": key}
      else:
        kw["prompt_cache_key"] = key
  return kw


# ------------------------------------------------------------- ADK models
def _single(s: ModelSpec, role: str | None = None, reasoning: str | None = None,
            cache_hints: bool = True, **extra) -> BaseLlm:
  if s.is_gemini:
    from google.adk.models.google_llm import Gemini
    return Gemini(model=s.litellm_model)
  try:
    from google.adk.models.lite_llm import LiteLlm
  except ImportError as e:
    raise ImportError("Non-Gemini models need LiteLLM: pip install 'adk-procedural-agent[llms]'") from e
  return LiteLlm(model=s.litellm_model, **s.kwargs, **provider_kwargs(s, role, reasoning, cache_hints), **extra)


class FallbackLlm(BaseLlm):
  """Tries each model in order; moves on when one fails before producing output."""

  model: str = "fallback"
  _chain: list = PrivateAttr(default_factory=list)

  def __init__(self, chain: list[BaseLlm], **data):
    super().__init__(model=" | ".join(m.model for m in chain), **data)
    self._chain = chain

  async def generate_content_async(self, llm_request, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
    last: Exception | None = None
    for i, m in enumerate(self._chain):
      started = False
      try:
        req = llm_request.model_copy(deep=True)
        req.model = m.model
        async for resp in m.generate_content_async(req, stream=stream):
          if resp.error_code and not started and i < len(self._chain) - 1:
            raise RuntimeError(f"{resp.error_code}: {resp.error_message}")
          started = True
          yield resp
        return
      except Exception as e:  # noqa: BLE001
        if started:
          raise
        last = e
        log.warning("model %s failed (%s); falling back", m.model, e)
    raise RuntimeError(f"All models failed; last error: {last}")


def build_model(spec: str, role: str | None = None, reasoning: str | None = None,
                cache_hints: bool = True, **extra) -> BaseLlm:
  chain = [_single(s, role, reasoning, cache_hints, **extra) for s in parse_chain(spec)]
  return chain[0] if len(chain) == 1 else FallbackLlm(chain)


# ------------------------------------------------------- JSON completions
async def complete_json(spec: str, prompt: str, schema: type[BaseModel], temperature: float = 0.2) -> dict:
  """Structured output from any provider in the spec chain (with fallback)."""
  last: Exception | None = None
  for s in parse_chain(spec):
    try:
      if s.is_gemini:
        from google import genai
        from google.genai import types
        resp = await genai.Client().aio.models.generate_content(
            model=s.litellm_model, contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json",
                                               response_schema=schema, temperature=temperature))
        return schema.model_validate_json(resp.text).model_dump()
      import litellm
      messages = [{"role": "system", "content": "Reply with JSON only, matching this JSON schema:\n"
                   + json.dumps(schema.model_json_schema())},
                  {"role": "user", "content": prompt}]
      try:
        resp = await litellm.acompletion(
            model=s.litellm_model, messages=messages, temperature=temperature,
            response_format={"type": "json_schema", "json_schema": {
                "name": schema.__name__, "schema": schema.model_json_schema()}}, **s.kwargs)
      except Exception:  # noqa: BLE001 - provider without json_schema support: plain JSON mode
        resp = await litellm.acompletion(model=s.litellm_model, messages=messages, temperature=temperature,
                                         response_format={"type": "json_object"}, **s.kwargs)
      return schema.model_validate_json(_strip_fences(resp.choices[0].message.content)).model_dump()
    except Exception as e:  # noqa: BLE001
      last = e
      log.warning("complete_json via %s failed: %s", s.raw, e)
  raise RuntimeError(f"All models failed for structured output: {last}")


async def complete_text(spec: str, prompt: str, temperature: float = 0.3) -> str:
  """Plain-text completion from any provider in the spec chain (with fallback)."""
  last: Exception | None = None
  for s in parse_chain(spec):
    try:
      if s.is_gemini:
        from google import genai
        from google.genai import types
        resp = await genai.Client().aio.models.generate_content(
            model=s.litellm_model, contents=prompt, config=types.GenerateContentConfig(temperature=temperature))
        return resp.text or ""
      import litellm
      resp = await litellm.acompletion(model=s.litellm_model, messages=[{"role": "user", "content": prompt}],
                                       temperature=temperature, **s.kwargs)
      return resp.choices[0].message.content or ""
    except Exception as e:  # noqa: BLE001
      last = e
      log.warning("complete_text via %s failed: %s", s.raw, e)
  raise RuntimeError(f"All models failed for text completion: {last}")


def _strip_fences(text: str) -> str:
  t = (text or "").strip()
  if t.startswith("```"):
    t = t.split("\n", 1)[1] if "\n" in t else t
    t = t.rsplit("```", 1)[0]
  return t.strip()


def describe(spec: str) -> list[dict[str, Any]]:
  """For diagnostics: what each spec resolves to (secrets masked)."""
  out = []
  for s in parse_chain(spec):
    kw = {k: ("***" if "key" in k else v) for k, v in s.kwargs.items()}
    out.append({"spec": s.raw, "provider": s.provider, "model": s.litellm_model, **kw})
  return out
