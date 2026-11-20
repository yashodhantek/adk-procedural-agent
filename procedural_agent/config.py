"""Runtime settings, all overridable through environment variables (.env)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
  return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
  return int(os.environ.get(name, default))


def _env_float(name: str, default: float) -> float:
  return float(os.environ.get(name, default))


def _env_bool(name: str, default: bool) -> bool:
  return os.environ.get(name, str(default)).lower() in ("1", "true", "yes", "on")


def _load_mcp_servers() -> list:
  servers = json.loads(_env("MCP_SERVERS", "[]") or "[]")
  path = Path(_env("MCP_SERVERS_FILE", "mcp_servers.json"))
  if path.exists():
    data = json.loads(path.read_text())
    servers += data.get("servers", data) if isinstance(data, dict) else data
  return servers


@dataclass(frozen=True)
class Settings:
  # --- Models (Gemini via google-genai; any LiteLlm string also works) -------
  model: str = field(default_factory=lambda: _env("AGENT_MODEL", "gemini-3.5-flash"))
  planner_model: str = field(default_factory=lambda: _env("PLANNER_MODEL", "gemini-3.1-pro"))
  critic_model: str = field(default_factory=lambda: _env("CRITIC_MODEL", "gemini-3.5-flash"))
  learner_model: str = field(default_factory=lambda: _env("LEARNER_MODEL", "gemini-3.5-flash"))
  summarizer_model: str = field(default_factory=lambda: _env("SUMMARIZER_MODEL", "gemini-3.5-flash"))

  # --- Storage ---------------------------------------------------------------
  data_dir: Path = field(default_factory=lambda: Path(_env("AGENT_DATA_DIR", ".data")).resolve())
  # sqlite (local, default) | vertex (Agent Engine sessions + Memory Bank)
  memory_backend: str = field(default_factory=lambda: _env("MEMORY_BACKEND", "sqlite"))
  agent_engine_id: str = field(default_factory=lambda: _env("GOOGLE_CLOUD_AGENT_ENGINE_ID", ""))

  # --- Harness loop ----------------------------------------------------------
  max_revisions: int = field(default_factory=lambda: _env_int("MAX_REVISIONS", 2))
  max_replans: int = field(default_factory=lambda: _env_int("MAX_REPLANS", 1))
  accept_score: float = field(default_factory=lambda: _env_float("ACCEPT_SCORE", 0.75))
  step_timeout_s: float = field(default_factory=lambda: _env_float("STEP_TIMEOUT_S", 20.0))
  max_parallel_steps: int = field(default_factory=lambda: _env_int("MAX_PARALLEL_STEPS", 8))

  # --- Self-learning ---------------------------------------------------------
  learning_enabled: bool = field(default_factory=lambda: _env_bool("LEARNING_ENABLED", True))
  # llm | heuristic   (heuristic needs no model credentials; used in tests)
  learner_mode: str = field(default_factory=lambda: _env("LEARNER_MODE", "llm"))
  promote_after: int = field(default_factory=lambda: _env_int("PROMOTE_AFTER", 3))
  deprecate_below: float = field(default_factory=lambda: _env_float("DEPRECATE_BELOW", 0.35))
  playbook_size: int = field(default_factory=lambda: _env_int("PLAYBOOK_SIZE", 12))

  # --- Context management ----------------------------------------------------
  compaction_interval: int = field(default_factory=lambda: _env_int("COMPACTION_INTERVAL", 6))
  compaction_overlap: int = field(default_factory=lambda: _env_int("COMPACTION_OVERLAP", 1))
  compaction_token_threshold: int = field(default_factory=lambda: _env_int("COMPACTION_TOKEN_THRESHOLD", 60000))
  compaction_keep_events: int = field(default_factory=lambda: _env_int("COMPACTION_KEEP_EVENTS", 12))
  context_cache: bool = field(default_factory=lambda: _env_bool("CONTEXT_CACHE", True))

  # --- Data sources ----------------------------------------------------------
  # Hosts the generic HTTP tool and procedures may call. "*" disables the check.
  http_allowlist: tuple[str, ...] = field(default_factory=lambda: tuple(
      h.strip() for h in _env(
          "HTTP_ALLOWLIST",
          "api.open-meteo.com,geocoding-api.open-meteo.com,api.frankfurter.app,"
          "air-quality-api.open-meteo.com,earthquake.usgs.gov,api.coingecko.com",
      ).split(",") if h.strip()))
  # auto | gemini | tavily | exa | brave | openai | none
  search_provider: str = field(default_factory=lambda: _env("SEARCH_PROVIDER", "auto"))
  # Model for gemini (Google Search grounding) or openai (web_search_options) search.
  search_model: str = field(default_factory=lambda: _env("SEARCH_MODEL", ""))
  search_max_results: int = field(default_factory=lambda: _env_int("SEARCH_MAX_RESULTS", 5))

  # --- Reasoning per role: off | auto | minimal | low | medium | high -----------
  # auto = on (medium) when the model is known to reason, otherwise off.
  # An explicit level forces it (use for Azure / TrueFoundry deployment names).
  planner_reasoning: str = field(default_factory=lambda: _env("PLANNER_REASONING", "auto"))
  agent_reasoning: str = field(default_factory=lambda: _env("AGENT_REASONING", "auto"))
  critic_reasoning: str = field(default_factory=lambda: _env("CRITIC_REASONING", "off"))
  # Prompt-based plan-then-act for a non-reasoning synthesizer model.
  plan_react_fallback: bool = field(default_factory=lambda: _env_bool("PLAN_REACT_FALLBACK", True))
  # Provider prompt caching hints (OpenAI/Azure prompt_cache_key, Anthropic cache_control).
  prompt_cache_hints: bool = field(default_factory=lambda: _env_bool("PROMPT_CACHE_HINTS", True))
  # MCP servers, from MCP_SERVERS (JSON) and/or MCP_SERVERS_FILE (a JSON file). Entries:
  #   {"name": "crm", "url": "https://host/mcp", "headers": {...}}          (streamable HTTP)
  #   {"name": "techintel", "command": "python", "args": [...], "env": {...}} (local stdio)
  # "${VAR}" inside env, headers, args and url is expanded from the environment.
  mcp_servers: list = field(default_factory=lambda: _load_mcp_servers())
  # Model for `LLM:` procedure steps (summarise / classify / draft). Defaults to LEARNER_MODEL.
  llm_step_model: str = field(default_factory=lambda: _env("LLM_STEP_MODEL", _env("LEARNER_MODEL", "gemini-3.5-flash")))
  approval_ttl_hours: float = field(default_factory=lambda: _env_float("APPROVAL_TTL_HOURS", 24.0))

  @property
  def db_path(self) -> Path:
    return self.data_dir / "agent_memory.sqlite"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
