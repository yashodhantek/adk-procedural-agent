"""Procedural memory as a knowledge graph.

Nodes
  Procedure  -- a reusable "how-to" (executable call spec and/or NL steps)
  Source     -- a real-time data source a procedure reads from
Edges
  DEPENDS_ON   procedure -> procedure  (mapping: {my_input: their_output})
  COMPOSED_OF  composite -> part       (learned macro procedures, AWM-style)
  USES_SOURCE  procedure -> source

The graph answers three questions for the planner/executor:
  * which procedures are relevant to a question        (search)
  * what a chosen procedure transitively needs          (dependency closure)
  * in which order / with what parallelism to run them  (compile -> levels)
and it learns: every execution updates reliability stats, learned
composites are promoted or deprecated, and successful plans are cached.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .store import SqliteStore, fts_query, jaccard, now, signature, tokens

SEED_FILE = Path(__file__).resolve().parent.parent / "seed" / "procedures.json"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS procedures (
  name TEXT PRIMARY KEY,
  domain TEXT NOT NULL DEFAULT 'general',
  description TEXT NOT NULL,
  inputs_json TEXT NOT NULL DEFAULT '[]',
  outputs_json TEXT NOT NULL DEFAULT '[]',
  steps_md TEXT NOT NULL DEFAULT '',
  call_json TEXT,
  status TEXT NOT NULL DEFAULT 'active',      -- active | candidate | deprecated
  origin TEXT NOT NULL DEFAULT 'seed',        -- seed | learned | user
  version INTEGER NOT NULL DEFAULT 1,
  success INTEGER NOT NULL DEFAULT 0,
  failure INTEGER NOT NULL DEFAULT 0,
  total_latency_ms REAL NOT NULL DEFAULT 0,
  created_at REAL, updated_at REAL, last_used REAL
);
CREATE TABLE IF NOT EXISTS sources (
  name TEXT PRIMARY KEY, kind TEXT, base_url TEXT, description TEXT,
  success INTEGER NOT NULL DEFAULT 0, failure INTEGER NOT NULL DEFAULT 0,
  total_latency_ms REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS edges (
  src TEXT NOT NULL, dst TEXT NOT NULL, type TEXT NOT NULL,
  mapping_json TEXT NOT NULL DEFAULT '{}', weight REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY (src, dst, type)
);
CREATE TABLE IF NOT EXISTS plan_cache (
  signature TEXT PRIMARY KEY, query TEXT, plan_json TEXT,
  successes INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0,
  updated_at REAL
);
"""

_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS procedures_fts USING fts5(
  name, domain, description, steps, io, tokenize='porter'
);
"""


@dataclass
class Procedure:
  name: str
  description: str
  domain: str = "general"
  inputs: list[str] = field(default_factory=list)
  outputs: list[str] = field(default_factory=list)
  steps_md: str = ""
  call: dict | None = None
  status: str = "active"
  origin: str = "seed"
  version: int = 1
  success: int = 0
  failure: int = 0
  total_latency_ms: float = 0.0

  @property
  def reliability(self) -> float:
    """Laplace-smoothed success rate."""
    return (self.success + 1) / (self.success + self.failure + 2)

  @property
  def executable(self) -> bool:
    return bool(self.call)

  def card(self) -> dict:
    return {
        "name": self.name, "domain": self.domain, "description": self.description,
        "inputs": self.inputs, "outputs": self.outputs, "status": self.status,
        "origin": self.origin, "reliability": round(self.reliability, 2),
        "executable": self.executable,
    }


class ProceduralKG:

  def __init__(self, store: SqliteStore, seed: bool = True):
    self.db = store
    self.db.executescript(_SCHEMA)
    if self.db.has_fts:
      self.db.executescript(_FTS)
    if seed and not self.db.query("SELECT 1 FROM procedures LIMIT 1"):
      self.load_seed(SEED_FILE)

  # ------------------------------------------------------------------ write
  def load_seed(self, path: Path) -> None:
    data = json.loads(Path(path).read_text())
    for s in data.get("sources", []):
      self.upsert_source(**s)
    for p in data.get("procedures", []):
      deps = p.pop("depends_on", {})
      parts = p.pop("composed_of", [])
      uses = p.pop("uses_source", None)
      self.upsert_procedure(Procedure(**p))
      for dep, mapping in deps.items():
        self.add_edge(p["name"], dep, "DEPENDS_ON", mapping)
      for part in parts:
        self.add_edge(p["name"], part, "COMPOSED_OF")
      if uses:
        self.add_edge(p["name"], uses, "USES_SOURCE")

  def upsert_source(self, name: str, kind: str, base_url: str = "", description: str = "") -> None:
    self.db.execute(
        "INSERT INTO sources(name, kind, base_url, description) VALUES (?,?,?,?) "
        "ON CONFLICT(name) DO UPDATE SET kind=excluded.kind, base_url=excluded.base_url, "
        "description=excluded.description",
        (name, kind, base_url, description))

  def upsert_procedure(self, p: Procedure) -> None:
    existing = self.get(p.name)
    ts = now()
    if existing:
      p.version = existing.version + 1
      self.db.execute(
          "UPDATE procedures SET domain=?, description=?, inputs_json=?, outputs_json=?, "
          "steps_md=?, call_json=?, status=?, origin=?, version=?, updated_at=? WHERE name=?",
          (p.domain, p.description, json.dumps(p.inputs), json.dumps(p.outputs), p.steps_md,
           json.dumps(p.call) if p.call else None, p.status, p.origin, p.version, ts, p.name))
    else:
      self.db.execute(
          "INSERT INTO procedures(name, domain, description, inputs_json, outputs_json, steps_md, "
          "call_json, status, origin, version, success, failure, created_at, updated_at) "
          "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
          (p.name, p.domain, p.description, json.dumps(p.inputs), json.dumps(p.outputs),
           p.steps_md, json.dumps(p.call) if p.call else None, p.status, p.origin, p.version,
           p.success, p.failure, ts, ts))
    if self.db.has_fts:
      self.db.execute("DELETE FROM procedures_fts WHERE name=?", (p.name,))
      self.db.execute(
          "INSERT INTO procedures_fts(name, domain, description, steps, io) VALUES (?,?,?,?,?)",
          (p.name, p.domain, p.description, p.steps_md,
           " ".join(p.inputs + p.outputs).replace("_", " ")))

  def add_edge(self, src: str, dst: str, type_: str, mapping: dict | None = None, weight: float = 1.0) -> None:
    if type_ in ("DEPENDS_ON", "COMPOSED_OF") and self._creates_cycle(src, dst, type_):
      raise ValueError(f"Edge {src} -{type_}-> {dst} would create a cycle")
    self.db.execute(
        "INSERT INTO edges(src, dst, type, mapping_json, weight) VALUES (?,?,?,?,?) "
        "ON CONFLICT(src, dst, type) DO UPDATE SET mapping_json=excluded.mapping_json, weight=excluded.weight",
        (src, dst, type_, json.dumps(mapping or {}), weight))

  def set_status(self, name: str, status: str) -> None:
    self.db.execute("UPDATE procedures SET status=?, updated_at=? WHERE name=?", (status, now(), name))

  def record_outcome(self, name: str, ok: bool, latency_ms: float = 0.0) -> None:
    col = "success" if ok else "failure"
    self.db.execute(
        f"UPDATE procedures SET {col}={col}+1, total_latency_ms=total_latency_ms+?, last_used=? WHERE name=?",
        (latency_ms, now(), name))

  def record_source_outcome(self, name: str, ok: bool, latency_ms: float = 0.0) -> None:
    col = "success" if ok else "failure"
    self.db.execute(
        f"UPDATE sources SET {col}={col}+1, total_latency_ms=total_latency_ms+? WHERE name=?",
        (latency_ms, name))

  # ------------------------------------------------------------------- read
  def _row(self, r) -> Procedure:
    return Procedure(
        name=r["name"], description=r["description"], domain=r["domain"],
        inputs=json.loads(r["inputs_json"]), outputs=json.loads(r["outputs_json"]),
        steps_md=r["steps_md"], call=json.loads(r["call_json"]) if r["call_json"] else None,
        status=r["status"], origin=r["origin"], version=r["version"],
        success=r["success"], failure=r["failure"], total_latency_ms=r["total_latency_ms"])

  def get(self, name: str) -> Procedure | None:
    rows = self.db.query("SELECT * FROM procedures WHERE name=?", (name,))
    return self._row(rows[0]) if rows else None

  def all(self, include_deprecated: bool = False) -> list[Procedure]:
    sql = "SELECT * FROM procedures" + ("" if include_deprecated else " WHERE status!='deprecated'")
    return [self._row(r) for r in self.db.query(sql)]

  def edges(self, src: str | None = None, type_: str | None = None, dst: str | None = None) -> list[dict]:
    sql, params = "SELECT * FROM edges WHERE 1=1", []
    for col, val in (("src", src), ("type", type_), ("dst", dst)):
      if val is not None:
        sql += f" AND {col}=?"
        params.append(val)
    return [dict(src=r["src"], dst=r["dst"], type=r["type"],
                 mapping=json.loads(r["mapping_json"]), weight=r["weight"])
            for r in self.db.query(sql, tuple(params))]

  def dependencies(self, name: str) -> list[str]:
    return [e["dst"] for e in self.edges(src=name, type_="DEPENDS_ON")]

  def parts(self, name: str) -> list[str]:
    return [e["dst"] for e in self.edges(src=name, type_="COMPOSED_OF")]

  def dependents(self, name: str) -> list[str]:
    return [e["src"] for e in self.edges(dst=name, type_="DEPENDS_ON")]

  def closure(self, name: str) -> list[str]:
    """All procedures `name` transitively depends on (deps first)."""
    seen, order = set(), []

    def visit(n: str):
      for d in self.dependencies(n) + self.parts(n):
        if d not in seen:
          seen.add(d)
          visit(d)
          order.append(d)
    visit(name)
    return order

  def _creates_cycle(self, src: str, dst: str, type_: str) -> bool:
    return src == dst or src in ([dst] + self.closure(dst))

  def search(self, query: str, k: int = 8, include_candidates: bool = True) -> list[Procedure]:
    """Hybrid lexical search (FTS5/bm25 when available) re-ranked by reliability."""
    names: list[str] = []
    if self.db.has_fts and tokens(query):
      rows = self.db.query(
          "SELECT name FROM procedures_fts WHERE procedures_fts MATCH ? ORDER BY bm25(procedures_fts) LIMIT ?",
          (fts_query(query), k * 3))
      names = [r["name"] for r in rows]
    pool = [p for p in (self.get(n) for n in names) if p] if names else self.all()
    scored = []
    for rank, p in enumerate(pool):
      if p.status == "deprecated" or (p.status == "candidate" and not include_candidates):
        continue
      text = f"{p.name.replace('_', ' ')} {p.description} {p.domain} {' '.join(p.inputs + p.outputs)}"
      lexical = jaccard(query, text) + (1.0 / (rank + 1) if names else 0.0)
      if lexical <= 0:
        continue
      bonus = 0.15 * p.reliability + (0.1 if p.origin == "learned" and p.status == "active" else 0)
      scored.append((lexical + bonus, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:k]]

  # ------------------------------------------------------------ plan cache
  def cached_plan(self, query: str, min_similarity: float = 0.8) -> dict | None:
    sig = signature(query)
    best, best_sim = None, 0.0
    for r in self.db.query("SELECT * FROM plan_cache WHERE successes > failures"):
      sim = 1.0 if r["signature"] == sig else jaccard(sig, r["signature"])
      if sim > best_sim:
        best, best_sim = r, sim
    if best is not None and best_sim >= min_similarity:
      return {"query": best["query"], "plan": json.loads(best["plan_json"]),
              "similarity": round(best_sim, 2), "successes": best["successes"]}
    return None

  def cache_plan(self, query: str, plan: dict, ok: bool) -> None:
    col = "successes" if ok else "failures"
    self.db.execute(
        f"INSERT INTO plan_cache(signature, query, plan_json, {col}, updated_at) VALUES (?,?,?,1,?) "
        f"ON CONFLICT(signature) DO UPDATE SET {col}={col}+1, plan_json=excluded.plan_json, "
        "updated_at=excluded.updated_at",
        (signature(query), query, json.dumps(plan), now()))

  # --------------------------------------------------------------- compile
  def compile(self, plan: dict) -> dict:
    """Validate a planner Plan against the graph and produce parallel levels.

    * composite (learned) procedures are expanded into their parts
    * missing dependencies are added automatically (dependency closure)
    * unknown procedures become 'adhoc' steps the synthesizer handles
    * steps are grouped into topological levels; a level runs in parallel
    """
    warnings: list[str] = []
    added: list[str] = []
    steps: dict[str, dict] = {}
    by_proc: dict[str, str] = {}

    def add_step(sid: str, proc: str, inputs: dict, depends_on: list[str], purpose: str) -> str:
      steps[sid] = {"id": sid, "procedure": proc, "inputs": dict(inputs),
                    "depends_on": list(dict.fromkeys(depends_on)), "purpose": purpose}
      if proc != "adhoc":
        by_proc.setdefault(proc, sid)
      return sid

    raw = plan.get("steps", [])
    for s in raw:
      inputs = {i["name"]: i["value"] for i in s.get("inputs", [])} if isinstance(s.get("inputs"), list) else dict(s.get("inputs") or {})
      proc = s.get("procedure") or "adhoc"
      p = self.get(proc) if proc != "adhoc" else None
      if proc != "adhoc" and (p is None or p.status == "deprecated"):
        warnings.append(f"Unknown or deprecated procedure '{proc}' -> handled ad hoc")
        proc = "adhoc"
      add_step(s["id"], proc, inputs, s.get("depends_on", []), s.get("purpose", ""))

    # Expand composites and close over dependencies until fixpoint.
    changed = True
    while changed:
      changed = False
      for sid in list(steps):
        st = steps[sid]
        proc = st["procedure"]
        if proc == "adhoc":
          continue
        for part in self.parts(proc):
          if part not in by_proc:
            new_id = f"{sid}_{part}"
            add_step(new_id, part, st["inputs"], [], f"part of {proc}")
            added.append(new_id)
            changed = True
          if by_proc[part] not in st["depends_on"]:
            st["depends_on"].append(by_proc[part])
            changed = True
        for dep in self.dependencies(proc):
          if dep not in by_proc:
            new_id = f"auto_{dep}"
            add_step(new_id, dep, st["inputs"], [], f"required by {proc}")
            added.append(new_id)
            changed = True
          if by_proc[dep] not in st["depends_on"] and by_proc[dep] != sid:
            st["depends_on"].append(by_proc[dep])
            changed = True

    for st in steps.values():
      unknown = [d for d in st["depends_on"] if d not in steps]
      if unknown:
        warnings.append(f"Step {st['id']} referenced unknown steps {unknown}")
      st["depends_on"] = [d for d in st["depends_on"] if d in steps]

    # Kahn topological levels.
    indeg = {sid: len(st["depends_on"]) for sid, st in steps.items()}
    children = defaultdict(list)
    for sid, st in steps.items():
      for d in st["depends_on"]:
        children[d].append(sid)
    level = sorted(s for s, n in indeg.items() if n == 0)
    levels: list[list[str]] = []
    while level:
      levels.append(level)
      nxt = []
      for sid in level:
        for c in children[sid]:
          indeg[c] -= 1
          if indeg[c] == 0:
            nxt.append(c)
      level = sorted(nxt)
    if sum(len(lv) for lv in levels) != len(steps):
      raise ValueError("Plan contains a dependency cycle: " +
                       ", ".join(s for s, n in indeg.items() if n > 0))

    return {"intent": plan.get("intent", ""), "domain": plan.get("domain", "general"),
            "answer_strategy": plan.get("answer_strategy", ""),
            "steps": steps, "levels": levels, "added": added, "warnings": warnings}

  # ---------------------------------------------------------------- export
  def to_mermaid(self) -> str:
    lines = ["graph LR"]
    for p in self.all(include_deprecated=True):
      shape = f"{p.name}[[{p.name}]]" if p.origin == "learned" else f"{p.name}[{p.name}]"
      lines.append(f"  {shape}")
    for e in self.edges():
      arrow = {"DEPENDS_ON": "-->|needs|", "COMPOSED_OF": "-.->|part|", "USES_SOURCE": "-->|reads|"}[e["type"]]
      lines.append(f"  {e['src']} {arrow} {e['dst']}")
    return "\n".join(lines)

  def stats(self) -> dict[str, Any]:
    procs = self.all(include_deprecated=True)
    return {
        "procedures": len(procs),
        "learned": sum(p.origin == "learned" for p in procs),
        "candidates": sum(p.status == "candidate" for p in procs),
        "deprecated": sum(p.status == "deprecated" for p in procs),
        "edges": len(self.edges()),
        "cached_plans": self.db.query("SELECT COUNT(*) c FROM plan_cache")[0]["c"],
    }
