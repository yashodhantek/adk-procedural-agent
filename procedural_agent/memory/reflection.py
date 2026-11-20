"""Reflective memory (Reflexion) and an evolving playbook (ACE-style context).

* lessons   -- short verbal self-critiques written after a failed or revised run
* playbook  -- curated strategy bullets injected into prompts; each bullet keeps
               helpful/harmful counters and is pruned when it stops helping
"""

from __future__ import annotations

from .store import SqliteStore, fts_query, jaccard, now, tokens

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  scope TEXT NOT NULL DEFAULT 'global',   -- global | procedure name | domain
  cue TEXT NOT NULL, lesson TEXT NOT NULL,
  uses INTEGER NOT NULL DEFAULT 0, created_at REAL
);
CREATE TABLE IF NOT EXISTS playbook (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  section TEXT NOT NULL DEFAULT 'strategy',  -- strategy | pitfall | formatting | source
  bullet TEXT NOT NULL UNIQUE,
  helpful INTEGER NOT NULL DEFAULT 0, harmful INTEGER NOT NULL DEFAULT 0,
  active INTEGER NOT NULL DEFAULT 1, created_at REAL, updated_at REAL
);
"""
_FTS = "CREATE VIRTUAL TABLE IF NOT EXISTS lessons_fts USING fts5(cue, lesson);"

DEFAULT_PLAYBOOK = [
    ("strategy", "Prefer executable procedures from the graph over ad-hoc web calls; they are faster and validated."),
    ("strategy", "Run independent data fetches in the same plan level so they execute in parallel."),
    ("pitfall", "Always state the timestamp or date of real-time data; never present stale values as current."),
    ("formatting", "Lead with the direct answer, then the supporting numbers with units."),
]


class ReflectionMemory:

  def __init__(self, store: SqliteStore):
    self.db = store
    self.db.executescript(_SCHEMA)
    if self.db.has_fts:
      self.db.executescript(_FTS)
    if not self.db.query("SELECT 1 FROM playbook LIMIT 1"):
      for section, bullet in DEFAULT_PLAYBOOK:
        self.add_bullet(bullet, section)

  # ----------------------------------------------------------------- lessons
  def add_lesson(self, cue: str, lesson: str, scope: str = "global") -> int | None:
    for r in self.db.query("SELECT id, lesson FROM lessons WHERE scope=?", (scope,)):
      if jaccard(r["lesson"], lesson) >= 0.7:   # de-duplicate near-identical lessons
        return r["id"]
    cur = self.db.execute("INSERT INTO lessons(scope, cue, lesson, created_at) VALUES (?,?,?,?)",
                          (scope, cue, lesson, now()))
    if self.db.has_fts:
      self.db.execute("INSERT INTO lessons_fts(rowid, cue, lesson) VALUES (?,?,?)",
                      (cur.lastrowid, cue, lesson))
    return cur.lastrowid

  def relevant(self, query: str, k: int = 4) -> list[dict]:
    rows = []
    if self.db.has_fts and tokens(query):
      rows = self.db.query(
          "SELECT l.* FROM lessons_fts JOIN lessons l ON l.id = lessons_fts.rowid "
          "WHERE lessons_fts MATCH ? ORDER BY bm25(lessons_fts) LIMIT ?", (fts_query(query), k))
    if not rows:
      rows = sorted(self.db.query("SELECT * FROM lessons"),
                    key=lambda r: jaccard(query, r["cue"] + " " + r["lesson"]), reverse=True)[:k]
      rows = [r for r in rows if jaccard(query, r["cue"] + " " + r["lesson"]) > 0]
    for r in rows:
      self.db.execute("UPDATE lessons SET uses=uses+1 WHERE id=?", (r["id"],))
    return [{"id": r["id"], "scope": r["scope"], "lesson": r["lesson"]} for r in rows]

  # ---------------------------------------------------------------- playbook
  def add_bullet(self, bullet: str, section: str = "strategy") -> int | None:
    for r in self.db.query("SELECT id, bullet FROM playbook"):
      if jaccard(r["bullet"], bullet) >= 0.7:
        return r["id"]
    ts = now()
    cur = self.db.execute(
        "INSERT OR IGNORE INTO playbook(section, bullet, created_at, updated_at) VALUES (?,?,?,?)",
        (section, bullet, ts, ts))
    return cur.lastrowid

  def playbook(self, limit: int = 12) -> list[dict]:
    rows = self.db.query(
        "SELECT * FROM playbook WHERE active=1 ORDER BY (helpful - harmful) DESC, id ASC LIMIT ?", (limit,))
    return [dict(r) for r in rows]

  def score_bullets(self, ids: list[int], helpful: bool) -> None:
    col = "helpful" if helpful else "harmful"
    for i in ids:
      self.db.execute(f"UPDATE playbook SET {col}={col}+1, updated_at=? WHERE id=?", (now(), i))

  def prune(self, min_net: int = -2) -> int:
    cur = self.db.execute("UPDATE playbook SET active=0 WHERE active=1 AND (helpful - harmful) <= ?", (min_net,))
    return cur.rowcount

  @staticmethod
  def render(bullets: list[dict]) -> str:
    return "\n".join(f"- [{b['section']}#{b['id']}] {b['bullet']}" for b in bullets)
