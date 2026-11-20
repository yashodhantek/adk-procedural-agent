"""Shared SQLite plumbing for the agent's own memory stores (KG, facts, reflections)."""

from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path

_STOP = {
    "a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "is", "are", "what",
    "how", "me", "my", "i", "it", "be", "with", "at", "by", "from", "this", "that",
    "can", "you", "please", "give", "show", "tell", "get", "about", "do", "does",
}


def tokens(text: str) -> list[str]:
  return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in _STOP and len(t) > 1]


def fts_query(text: str) -> str:
  """OR-query of quoted tokens, safe for FTS5 MATCH."""
  toks = tokens(text)
  return " OR ".join(f'"{t}"' for t in dict.fromkeys(toks)) or '""'


def signature(text: str) -> str:
  """Order-insensitive intent signature used for plan caching."""
  return " ".join(sorted(set(tokens(text))))


def jaccard(a: str, b: str) -> float:
  sa, sb = set(tokens(a)), set(tokens(b))
  return len(sa & sb) / len(sa | sb) if sa and sb else 0.0


def now() -> float:
  return time.time()


class SqliteStore:
  """A thread-safe sqlite connection with FTS5 detection."""

  def __init__(self, path: str | Path):
    self.path = str(path)
    if self.path != ":memory:":
      Path(self.path).parent.mkdir(parents=True, exist_ok=True)
    self.conn = sqlite3.connect(self.path, check_same_thread=False)
    self.conn.row_factory = sqlite3.Row
    self.conn.execute("PRAGMA journal_mode=WAL")
    self.conn.execute("PRAGMA foreign_keys=ON")
    self.lock = threading.RLock()
    try:
      self.conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x)")
      self.conn.execute("DROP TABLE _fts_probe")
      self.has_fts = True
    except sqlite3.OperationalError:
      self.has_fts = False

  def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
    with self.lock:
      cur = self.conn.execute(sql, params)
      self.conn.commit()
      return cur

  def executescript(self, sql: str) -> None:
    with self.lock:
      self.conn.executescript(sql)
      self.conn.commit()

  def query(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
    with self.lock:
      return self.conn.execute(sql, params).fetchall()
