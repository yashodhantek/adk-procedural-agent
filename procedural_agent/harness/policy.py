"""Standing approvals: operator-written rules that pre-approve specific writes.

Scheduled runs have nobody to type "approve CODE". A standing approval lets one
named procedure run its write step unattended, but only within the bounds the
operator wrote down:

    approvals_policy.json  (git-ignored; path: APPROVALS_POLICY_FILE)
    [
      {"procedure": "techintel_email_brief",
       "args": {"to": ["srini@yashodhantek.com"]},      # every listed arg must match
       "users": ["srini"],                              # optional: who may trigger it
       "until": "2027-05-21",                           # required expiry (YYYY-MM-DD)
       "note": "daily Signal brief to myself"}
    ]

Rules
  * only side_effect "write" qualifies; "destructive" always needs a human
  * the procedure name must match exactly
  * each constrained argument must be present and every value in it allowed
    (comma/semicolon lists such as recipient lists are checked item by item)
  * entries without "until", or past it, are ignored
  * the agent cannot create or change this file: it is read-only to every tool
Every policy-approved execution is still recorded in pending_actions with the
exact arguments and the rule that allowed it.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import re
from pathlib import Path
from typing import Any

from ..config import settings

log = logging.getLogger(__name__)


def load_policies(path: str | Path | None = None) -> list[dict]:
  p = Path(path or settings.approvals_policy_file)
  if not p.exists():
    return []
  try:
    data = json.loads(p.read_text())
  except json.JSONDecodeError as e:
    log.error("Ignoring %s: invalid JSON (%s)", p, e)
    return []
  rules = data.get("rules", data) if isinstance(data, dict) else data
  return [dict(r, _index=i) for i, r in enumerate(rules) if isinstance(r, dict)]


def _values(v: Any) -> list[str]:
  if isinstance(v, (list, tuple)):
    return [str(x).strip().lower() for x in v]
  return [x.strip().lower() for x in re.split(r"[,;]", str(v)) if x.strip()]


def _call_args(call: dict) -> dict:
  if call.get("kind") == "mcp_tool":
    return call.get("args", {})
  if call.get("kind") == "http_json":
    return call.get("params", {})
  return {}


def match(procedure: str, side_effect: str, rendered_call: dict, user_id: str | None = None,
          rules: list[dict] | None = None, today: dt.date | None = None) -> dict | None:
  """The first rule that allows this exact call, or None."""
  if side_effect != "write":
    return None
  today = today or dt.date.today()
  args = _call_args(rendered_call)
  for rule in (rules if rules is not None else load_policies()):
    if rule.get("procedure") != procedure:
      continue
    try:
      until = dt.date.fromisoformat(str(rule.get("until", "")))
    except ValueError:
      log.warning("Standing approval #%s for %s has no valid 'until'; ignored", rule.get("_index"), procedure)
      continue
    if today > until:
      continue
    if rule.get("users") and user_id not in rule["users"]:
      continue
    ok = True
    for name, allowed in (rule.get("args") or {}).items():
      if name not in args:
        ok = False
        break
      allowed_set = set(_values(allowed))
      if not set(_values(args[name])) <= allowed_set or not _values(args[name]):
        ok = False
        break
    if ok:
      return rule
  return None
