"""Pending actions: procedure steps with side effects wait here for a human yes.

A step whose call spec says `"side_effect": "write"` or `"destructive"` is never
executed during planning. The executor renders the exact call (tool + final
arguments), stores it here under a short code, and the answer shows the user
the preview and the code. Only an explicit approval executes the stored call:
  * chat:  the user's own message contains "approve <code>" (checked by the tool,
           so the model cannot approve on the user's behalf)
  * CLI:   /approve <code>   ·   python scripts/approve.py <code>
"""

from __future__ import annotations

import json
import secrets
import time

from .store import SqliteStore, now

_SCHEMA = """
CREATE TABLE IF NOT EXISTS pending_actions (
  code TEXT PRIMARY KEY,
  user_id TEXT, session_id TEXT,
  procedure TEXT NOT NULL, side_effect TEXT NOT NULL,
  call_json TEXT NOT NULL,          -- fully rendered call: no templates left
  summary TEXT,
  status TEXT NOT NULL DEFAULT 'pending',   -- pending | executed | failed | rejected | expired
  result_json TEXT,
  created_at REAL, decided_at REAL
);
"""

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class Approvals:

  def __init__(self, store: SqliteStore):
    self.db = store
    self.db.executescript(_SCHEMA)

  def create(self, procedure: str, side_effect: str, call: dict, summary: str,
             user_id: str | None = None, session_id: str | None = None) -> str:
    code = "".join(secrets.choice(_ALPHABET) for _ in range(6))
    self.db.execute(
        "INSERT INTO pending_actions(code, user_id, session_id, procedure, side_effect, call_json, summary, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (code, user_id, session_id, procedure, side_effect, json.dumps(call, default=str), summary, now()))
    return code

  def get(self, code: str) -> dict | None:
    rows = self.db.query("SELECT * FROM pending_actions WHERE code=?", (code.upper().strip(),))
    if not rows:
      return None
    r = dict(rows[0])
    r["call"] = json.loads(r.pop("call_json"))
    r["result"] = json.loads(r["result_json"]) if r.get("result_json") else None
    return r

  def pending(self, user_id: str | None = None) -> list[dict]:
    sql, params = "SELECT code FROM pending_actions WHERE status='pending'", ()
    if user_id:
      sql, params = sql + " AND user_id=?", (user_id,)
    return [self.get(r["code"]) for r in self.db.query(sql + " ORDER BY created_at", params)]

  def decide(self, code: str, status: str, result: dict | None = None) -> None:
    self.db.execute("UPDATE pending_actions SET status=?, result_json=?, decided_at=? WHERE code=?",
                    (status, json.dumps(result, default=str) if result is not None else None, now(), code.upper()))

  def check(self, code: str, ttl_hours: float, user_id: str | None = None) -> dict:
    a = self.get(code)
    if not a:
      raise KeyError(f"No pending action {code}")
    if user_id and a["user_id"] and a["user_id"] != user_id:
      raise PermissionError("This action belongs to another user")
    if a["status"] != "pending":
      raise ValueError(f"Action {code} is already {a['status']}")
    if time.time() - (a["created_at"] or 0) > ttl_hours * 3600:
      self.decide(code, "expired")
      raise ValueError(f"Action {code} expired; run the request again")
    return a
