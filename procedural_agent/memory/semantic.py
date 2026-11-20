"""Semantic memory: durable facts about the user and the domain.

Short user-profile facts are also mirrored into `user:` session state so ADK
carries them across every session of that user automatically.
"""

from __future__ import annotations

from .store import SqliteStore, fts_query, jaccard, now, tokens

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL, subject TEXT NOT NULL, fact TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'fact',        -- fact | preference | domain
  confidence REAL NOT NULL DEFAULT 1.0,
  created_at REAL, updated_at REAL,
  UNIQUE(user_id, subject, fact)
);
"""
_FTS = "CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(subject, fact);"


class SemanticMemory:

  def __init__(self, store: SqliteStore):
    self.db = store
    self.db.executescript(_SCHEMA)
    if self.db.has_fts:
      self.db.executescript(_FTS)

  def remember(self, user_id: str, subject: str, fact: str, kind: str = "fact", confidence: float = 1.0) -> int:
    ts = now()
    # Supersede: a newer fact on the same subject+kind with high overlap replaces the old one.
    for r in self.db.query("SELECT id, fact FROM facts WHERE user_id=? AND subject=? AND kind=?",
                           (user_id, subject, kind)):
      if jaccard(r["fact"], fact) >= 0.6:
        self.db.execute("UPDATE facts SET fact=?, confidence=?, updated_at=? WHERE id=?",
                        (fact, confidence, ts, r["id"]))
        self._reindex(r["id"], subject, fact)
        return r["id"]
    cur = self.db.execute(
        "INSERT OR IGNORE INTO facts(user_id, subject, fact, kind, confidence, created_at, updated_at) "
        "VALUES (?,?,?,?,?,?,?)", (user_id, subject, fact, kind, confidence, ts, ts))
    fid = cur.lastrowid
    self._reindex(fid, subject, fact)
    return fid

  def _reindex(self, fid: int, subject: str, fact: str) -> None:
    if self.db.has_fts and fid:
      self.db.execute("DELETE FROM facts_fts WHERE rowid=?", (fid,))
      self.db.execute("INSERT INTO facts_fts(rowid, subject, fact) VALUES (?,?,?)", (fid, subject, fact))

  def search(self, user_id: str, query: str, k: int = 6) -> list[dict]:
    rows = []
    if self.db.has_fts and tokens(query):
      rows = self.db.query(
          "SELECT f.* FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
          "WHERE facts_fts MATCH ? AND f.user_id=? ORDER BY bm25(facts_fts) LIMIT ?",
          (fts_query(query), user_id, k))
    if not rows:
      rows = sorted(self.db.query("SELECT * FROM facts WHERE user_id=?", (user_id,)),
                    key=lambda r: jaccard(query, f"{r['subject']} {r['fact']}"), reverse=True)[:k]
    prefs = self.db.query("SELECT * FROM facts WHERE user_id=? AND kind='preference'", (user_id,))
    seen, out = set(), []
    for r in list(prefs) + list(rows):
      if r["id"] not in seen:
        seen.add(r["id"])
        out.append({"id": r["id"], "subject": r["subject"], "fact": r["fact"], "kind": r["kind"]})
    return out[: k + len(prefs)]

  def forget(self, user_id: str, fact_id: int) -> bool:
    cur = self.db.execute("DELETE FROM facts WHERE id=? AND user_id=?", (fact_id, user_id))
    if self.db.has_fts:
      self.db.execute("DELETE FROM facts_fts WHERE rowid=?", (fact_id,))
    return cur.rowcount > 0
