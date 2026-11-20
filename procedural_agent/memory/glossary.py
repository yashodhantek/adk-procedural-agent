"""Domain glossary: the shared vocabulary between users, documents and procedures.

Three kinds of entry
  parameter  canonical input/output names ("latitude" <- "lat", "lng"), with an
             optional value format (lower/upper) and unit
  value      canonical values for parameters ("INR" <- "rupees", "₹") scoped to
             the parameters they apply to (from_currency, to_currency, ...)
  concept    domain terms with definitions ("AQI"), linked to procedures

Used by
  * recall / planner   - terms found in the question + definitions go into the prompt
  * compile_plan       - step inputs are normalised to canonical values
  * search             - queries are expanded with canonical terms and linked procedures
  * ingestion          - extracted I/O names are canonicalised so edges can be matched
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .store import SqliteStore, now

SEED_FILE = Path(__file__).resolve().parent.parent / "seed" / "glossary.json"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS terms (
  canonical TEXT NOT NULL,
  kind TEXT NOT NULL,                 -- parameter | value | concept
  definition TEXT NOT NULL DEFAULT '',
  domain TEXT NOT NULL DEFAULT 'general',
  scope_json TEXT NOT NULL DEFAULT '[]',   -- value: parameters it applies to
  format TEXT,                        -- parameter: lower | upper | null
  unit TEXT,
  origin TEXT NOT NULL DEFAULT 'seed',
  updated_at REAL,
  PRIMARY KEY (canonical, kind)
);
CREATE TABLE IF NOT EXISTS term_aliases (
  alias TEXT NOT NULL, canonical TEXT NOT NULL, kind TEXT NOT NULL,
  PRIMARY KEY (alias, kind, canonical)
);
CREATE TABLE IF NOT EXISTS term_links (
  canonical TEXT NOT NULL, procedure TEXT NOT NULL,
  PRIMARY KEY (canonical, procedure)
);
"""


def _norm(text: str) -> str:
  return re.sub(r"\s+", " ", (text or "").strip().lower())


class Glossary:

  def __init__(self, store: SqliteStore, seed: bool = True):
    self.db = store
    self.db.executescript(_SCHEMA)
    if seed and not self.db.query("SELECT 1 FROM terms LIMIT 1") and SEED_FILE.exists():
      self.load(json.loads(SEED_FILE.read_text()))

  # ------------------------------------------------------------------ write
  def load(self, data: dict, origin: str = "seed") -> int:
    n = 0
    for p in data.get("parameters", []):
      self.define(p["name"], "parameter", p.get("definition", ""), p.get("aliases", []),
                  domain=p.get("domain", "general"), fmt=p.get("format"), unit=p.get("unit"), origin=origin)
      n += 1
    for v in data.get("values", []):
      self.define(v["canonical"], "value", v.get("definition", ""), v.get("aliases", []),
                  scope=v.get("scope", []), domain=v.get("domain", "general"), origin=origin)
      n += 1
    for c in data.get("concepts", []):
      self.define(c["term"], "concept", c.get("definition", ""), c.get("aliases", []),
                  domain=c.get("domain", "general"), links=c.get("related_procedures", []), origin=origin)
      n += 1
    return n

  def define(self, canonical: str, kind: str, definition: str = "", aliases: list[str] | None = None, *,
             scope: list[str] | None = None, domain: str = "general", fmt: str | None = None,
             unit: str | None = None, links: list[str] | None = None, origin: str = "user") -> None:
    if kind not in ("parameter", "value", "concept"):
      raise ValueError("kind must be parameter, value or concept")
    if kind == "parameter":
      canonical = re.sub(r"[^a-z0-9_]+", "_", canonical.lower()).strip("_")
    existing = self.get(canonical, kind)
    if existing:   # merge: keep old definition unless a new one is given, union scopes
      definition = definition or existing["definition"]
      scope = sorted(set(existing["scope"]) | set(scope or []))
      fmt, unit = fmt or existing["format"], unit or existing["unit"]
    self.db.execute(
        "INSERT INTO terms(canonical, kind, definition, domain, scope_json, format, unit, origin, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(canonical, kind) DO UPDATE SET definition=excluded.definition, "
        "domain=excluded.domain, scope_json=excluded.scope_json, format=excluded.format, unit=excluded.unit, "
        "updated_at=excluded.updated_at",
        (canonical, kind, definition, domain, json.dumps(scope or []), fmt, unit, origin, now()))
    for a in {canonical, *(aliases or [])}:
      self.db.execute("INSERT OR IGNORE INTO term_aliases(alias, canonical, kind) VALUES (?,?,?)",
                      (_norm(a), canonical, kind))
    for proc in links or []:
      self.db.execute("INSERT OR IGNORE INTO term_links(canonical, procedure) VALUES (?,?)", (canonical, proc))

  # ------------------------------------------------------------------- read
  def get(self, canonical: str, kind: str) -> dict | None:
    rows = self.db.query("SELECT * FROM terms WHERE canonical=? AND kind=?", (canonical, kind))
    if not rows:
      return None
    r = rows[0]
    return {"canonical": r["canonical"], "kind": r["kind"], "definition": r["definition"],
            "domain": r["domain"], "scope": json.loads(r["scope_json"]), "format": r["format"],
            "unit": r["unit"], "origin": r["origin"],
            "aliases": [a["alias"] for a in self.db.query(
                "SELECT alias FROM term_aliases WHERE canonical=? AND kind=?", (canonical, kind))],
            "procedures": [l["procedure"] for l in self.db.query(
                "SELECT procedure FROM term_links WHERE canonical=?", (canonical,))]}

  def lookup(self, text: str) -> list[dict]:
    rows = self.db.query("SELECT DISTINCT canonical, kind FROM term_aliases WHERE alias=?", (_norm(text),))
    return [self.get(r["canonical"], r["kind"]) for r in rows]

  def canonical_param(self, name: str) -> str:
    """'lat' -> 'latitude'; unknown names are returned snake_cased."""
    key = _norm(name).replace(" ", "_")
    for cand in (key, key.replace("_", " ")):
      rows = self.db.query("SELECT canonical FROM term_aliases WHERE alias=? AND kind='parameter'", (cand,))
      if rows:
        return rows[0]["canonical"]
    return re.sub(r"[^a-z0-9_]+", "_", key).strip("_")

  def normalize_value(self, param: str, value):
    """'rupees' for to_currency -> 'INR'; applies the parameter's format."""
    if not isinstance(value, str):
      return value
    param = self.canonical_param(param)
    out = value
    for r in self.db.query("SELECT canonical FROM term_aliases WHERE alias=? AND kind='value'", (_norm(value),)):
      term = self.get(r["canonical"], "value")
      if not term["scope"] or param in term["scope"]:
        out = term["canonical"]
        break
    p = self.get(param, "parameter")
    if p and p["format"] == "lower":
      out = out.lower()
    elif p and p["format"] == "upper":
      out = out.upper()
    return out

  def resolve(self, text: str, max_ngram: int = 4, kinds: tuple[str, ...] = ("value", "concept")) -> list[dict]:
    """Find glossary terms mentioned in free text (longest match wins).

    Parameter aliases ("to", "from", "value") are skipped by default: in prose
    they are ordinary words."""
    marks = ",".join("?" * len(kinds))
    words = re.findall(r"[\w$€₹£¥.]+|[$€₹£¥]", (text or "").lower())
    found: dict[tuple, dict] = {}
    i = 0
    while i < len(words):
      matched = False
      for n in range(min(max_ngram, len(words) - i), 0, -1):
        phrase = " ".join(words[i:i + n]).strip(".")
        rows = self.db.query(f"SELECT DISTINCT canonical, kind FROM term_aliases WHERE alias=? AND kind IN ({marks})",
                             (phrase, *kinds))
        if rows:
          for r in rows:
            term = self.get(r["canonical"], r["kind"])
            found[(term["canonical"], term["kind"])] = term | {"matched": phrase}
          i += n
          matched = True
          break
      if not matched:
        i += 1
    return list(found.values())

  def expand_query(self, text: str) -> str:
    """Append canonical names and linked procedures so lexical search finds them."""
    extra = []
    for t in self.resolve(text):
      extra.append(t["canonical"].replace("_", " "))
      extra += [p.replace("_", " ") for p in t["procedures"]]
    return text + (" " + " ".join(extra) if extra else "")

  def all(self, kind: str | None = None) -> list[dict]:
    sql = "SELECT canonical, kind FROM terms" + (" WHERE kind=?" if kind else "")
    return [self.get(r["canonical"], r["kind"]) for r in self.db.query(sql, (kind,) if kind else ())]

  @staticmethod
  def render(terms: list[dict]) -> list[dict]:
    """Compact form for prompts."""
    out = []
    for t in terms:
      item = {"said": t.get("matched"), "means": t["canonical"], "kind": t["kind"]}
      if t["definition"]:
        item["definition"] = t["definition"][:240]
      if t["kind"] == "value" and t["scope"]:
        item["for"] = t["scope"]
      if t["procedures"]:
        item["procedures"] = t["procedures"]
      out.append(item)
    return out
