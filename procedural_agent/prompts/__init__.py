"""Versioned prompt registry.

Defaults live next to this file. Optimised versions (written by
scripts/improve.py, e.g. from ADK's GEPA optimizer) live in
$AGENT_DATA_DIR/prompts/<name>/vN.md with an `active` pointer, so a prompt can
be promoted or rolled back without a redeploy.
"""

from __future__ import annotations

import json
from pathlib import Path

from ..config import settings

_DEFAULTS = Path(__file__).resolve().parent
_STORE = settings.data_dir / "prompts"


def _dir(name: str) -> Path:
  return _STORE / name


def active_version(name: str) -> int:
  ptr = _dir(name) / "active.json"
  return json.loads(ptr.read_text())["version"] if ptr.exists() else 0


def load(name: str) -> str:
  v = active_version(name)
  if v:
    return (_dir(name) / f"v{v}.md").read_text()
  return (_DEFAULTS / f"{name}.md").read_text()


def save_version(name: str, text: str, note: str = "", activate: bool = True) -> int:
  d = _dir(name)
  d.mkdir(parents=True, exist_ok=True)
  versions = sorted(int(p.stem[1:]) for p in d.glob("v*.md"))
  v = (versions[-1] if versions else 0) + 1
  (d / f"v{v}.md").write_text(text)
  (d / f"v{v}.note").write_text(note)
  if activate:
    (d / "active.json").write_text(json.dumps({"version": v}))
  return v


def rollback(name: str, version: int = 0) -> None:
  """version=0 returns to the shipped default."""
  ptr = _dir(name) / "active.json"
  if version == 0:
    ptr.unlink(missing_ok=True)
  else:
    ptr.write_text(json.dumps({"version": version}))


DYNAMIC_MARKER = "<!-- dynamic -->"


def _fill(text: str, values: dict) -> str:
  for k, v in values.items():
    text = text.replace("{{" + k + "}}", v or "(none yet)")
  return text


def render(name: str, **values: str) -> str:
  """Whole prompt (static + dynamic), as one string."""
  return _fill(load(name).replace(DYNAMIC_MARKER + "\n", ""), values)


def split(name: str) -> tuple[str, str]:
  """(static, dynamic template). The static part never changes between calls, so it
  is sent as ADK's static_instruction: a stable prefix that provider prompt caches
  (OpenAI/Azure automatic, Anthropic cache_control, Gemini context cache) can reuse."""
  text = load(name)
  static, _, dynamic = text.partition(DYNAMIC_MARKER)
  return static.rstrip() + "\n", dynamic.lstrip("\n")


def render_dynamic(name: str, **values: str) -> str:
  return _fill(split(name)[1], values)
