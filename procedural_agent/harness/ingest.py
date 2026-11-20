"""Natural language -> procedural knowledge graph.

    text ─▶ extract ─▶ canonicalise ─▶ resolve/dedupe ─▶ infer edges ─▶ validate calls ─▶ stage ─▶ apply
           (LLM or      (glossary)      (search the       (text + I/O      (allowlist,     (review   (graph,
           cards)                       existing graph)   matching)        dry run)        report)   glossary)

Two extractors:
  * CardExtractor  - deterministic parser for "procedure cards" (see README); no model needed
  * LlmExtractor   - Gemini with a strict schema for free-form SOPs and runbooks
Nothing touches the graph until `apply()`; edges inferred only from I/O
matching wait for approval, and new procedures enter as `candidate`.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from collections import defaultdict
from typing import Literal
from urllib.parse import parse_qsl, urlparse

from pydantic import BaseModel, Field

from ..config import settings
from ..memory import Procedure
from ..memory.store import jaccard, now
from .executor import execute_call, template_vars
from .learner import safe_name

log = logging.getLogger(__name__)


# ------------------------------------------------------------------ schemas
class KV(BaseModel):
  name: str
  value: str


class DraftCall(BaseModel):
  url: str = Field(default="", description="Endpoint with {input} placeholders; empty if no API is named")
  params: list[KV] = Field(default_factory=list, description="Query parameters, values may use {input}")
  extract: list[KV] = Field(default_factory=list, description="output name -> JSON path like results.0.lat")
  required: list[str] = Field(default_factory=list)
  expr: str = Field(default="", description="Arithmetic over inputs if the step is a calculation")


class DraftDependency(BaseModel):
  target: str = Field(description="Name or description of the procedure needed")
  relation: Literal["needs", "made_of"] = "needs"
  mapping: list[KV] = Field(default_factory=list, description="name=my input, value=their output")


class DraftProcedure(BaseModel):
  name: str
  description: str
  domain: str = "general"
  inputs: list[str] = Field(default_factory=list)
  outputs: list[str] = Field(default_factory=list)
  steps_md: str = ""
  call: DraftCall | None = None
  depends_on: list[DraftDependency] = Field(default_factory=list)
  sample_inputs: list[KV] = Field(default_factory=list, description="Example input values for a test call")
  evidence: str = Field(default="", description="Short quote from the text this came from")


class DraftTerm(BaseModel):
  term: str
  kind: Literal["parameter", "value", "concept"] = "concept"
  definition: str = ""
  aliases: list[str] = Field(default_factory=list)
  applies_to: list[str] = Field(default_factory=list)
  related_procedures: list[str] = Field(default_factory=list)


class Extraction(BaseModel):
  procedures: list[DraftProcedure] = Field(default_factory=list)
  terms: list[DraftTerm] = Field(default_factory=list)


# ---------------------------------------------------------------- extractors
_FIELD = re.compile(r"^(description|domain|inputs|outputs|needs|made of|api|extract|required|sample|"
                    r"compute|kind|aliases|definition|applies to|related|steps)\s*:\s*(.*)$", re.I)


def _split_list(text: str) -> list[str]:
  """Split on , or ; outside parentheses."""
  out, depth, cur = [], 0, ""
  for ch in text or "":
    depth += ch == "("
    depth -= ch == ")"
    if ch in ",;" and depth == 0:
      out.append(cur)
      cur = ""
    else:
      cur += ch
  return [x.strip() for x in out + [cur] if x.strip()]


def _pairs(text: str, sep: str = "=") -> list[KV]:
  out = []
  for part in re.split(r"[;\n]", text or ""):
    if sep in part:
      k, v = part.split(sep, 1)
      out.append(KV(name=k.strip(), value=v.strip()))
  return out


class CardExtractor:
  """Parses '## Procedure: name' and '## Term: name' blocks."""

  @staticmethod
  def applies(text: str) -> bool:
    return bool(re.search(r"^##\s*(procedure|term)\s*:", text, re.I | re.M))

  async def extract(self, text: str, context: dict | None = None) -> Extraction:
    ex = Extraction()
    blocks = re.split(r"^##\s*", text, flags=re.M)
    for block in blocks:
      head, _, body = block.partition("\n")
      m = re.match(r"(procedure|term)\s*:\s*(.+)", head.strip(), re.I)
      if not m:
        continue
      fields: dict[str, str] = {}
      steps: list[str] = []
      in_steps = False
      for line in body.splitlines():
        fm = _FIELD.match(line.strip())
        if fm and not (in_steps and re.match(r"^\s*\d+[.)]", line)):
          key, val = fm.group(1).lower(), fm.group(2).strip()
          in_steps = key == "steps"
          if not in_steps:
            fields[key] = val
          elif val:
            steps.append(val)
        elif in_steps and line.strip():
          steps.append(line.strip())
      if m.group(1).lower() == "term":
        ex.terms.append(DraftTerm(
            term=m.group(2).strip(), kind=(fields.get("kind") or "concept").lower(),
            definition=fields.get("definition", ""), aliases=_split_list(fields.get("aliases", "")),
            applies_to=_split_list(fields.get("applies to", "")),
            related_procedures=_split_list(fields.get("related", ""))))
        continue
      call = None
      if api := fields.get("api"):
        url = re.sub(r"^(GET|POST)\s+", "", api, flags=re.I).strip()
        parsed = urlparse(url.replace("{", "%7B").replace("}", "%7D"))
        base = url.split("?", 1)[0]
        params = [KV(name=k, value=v.replace("%7B", "{").replace("%7D", "}"))
                  for k, v in parse_qsl(parsed.query, keep_blank_values=True)]
        call = DraftCall(url=base, params=params, extract=_pairs(fields.get("extract", "")),
                         required=_split_list(fields.get("required", "")))
      elif expr := fields.get("compute"):
        call = DraftCall(expr=expr, required=[])
      deps = []
      for d in _split_list(fields.get("needs", "")):
        dm = re.match(r"([^()]+)\(([^)]*)\)", d)
        name, maps = (dm.group(1).strip(), dm.group(2)) if dm else (d, "")
        deps.append(DraftDependency(target=name, relation="needs", mapping=_pairs(maps.replace(",", ";"), "->")))
      deps += [DraftDependency(target=p, relation="made_of") for p in _split_list(fields.get("made of", ""))]
      ex.procedures.append(DraftProcedure(
          name=m.group(2).strip(), description=fields.get("description", m.group(2).strip()),
          domain=fields.get("domain", "general"), inputs=_split_list(fields.get("inputs", "")),
          outputs=_split_list(fields.get("outputs", "")), steps_md="\n".join(steps), call=call,
          depends_on=deps, sample_inputs=_pairs(fields.get("sample", "")), evidence=head.strip()))
    return ex


class LlmExtractor:
  """Free text -> Extraction with Gemini structured output."""

  def __init__(self, model: str | None = None):
    from .. import llm
    self.model = model or settings.learner_model
    llm.parse_chain(self.model)

  async def extract(self, text: str, context: dict | None = None) -> Extraction:
    from .. import llm
    ctx = context or {}
    prompt = (
        "Extract reusable PROCEDURES (how to get or compute something) and GLOSSARY TERMS "
        "from the document below, for an agent's procedural knowledge graph.\n"
        "- One procedure per distinct task. Use snake_case verb_noun names.\n"
        "- inputs/outputs are parameter names; reuse KNOWN PARAMETERS where the meaning matches.\n"
        "- depends_on: tasks that must happen first ('after X', 'using the result of X'); prefer "
        "KNOWN PROCEDURES names. relation=made_of when the task is a bundle of other tasks.\n"
        "- call: only if the text names an API endpoint or a formula; put {input} placeholders in it.\n"
        "- Do not invent endpoints or facts that are not in the text. Quote evidence briefly.\n"
        "- terms: domain vocabulary, synonyms, codes and their meanings.\n\n"
        f"KNOWN PROCEDURES: {ctx.get('procedures', [])}\nKNOWN PARAMETERS: {ctx.get('parameters', [])}\n\n"
        f"DOCUMENT:\n{text}")
    return Extraction.model_validate(await llm.complete_json(self.model, prompt, Extraction, temperature=0.1))


def chunk(text: str, max_chars: int = 6000) -> list[str]:
  sections = re.split(r"(?=^#{1,2}\s)", text, flags=re.M)
  chunks, cur = [], ""
  for s in sections:
    if len(cur) + len(s) > max_chars and cur:
      chunks.append(cur)
      cur = ""
    cur += s
  return chunks + ([cur] if cur.strip() else [])


# ------------------------------------------------------------------ ingestor
_BATCH_SCHEMA = """
CREATE TABLE IF NOT EXISTS ingest_batches (
  id TEXT PRIMARY KEY, source TEXT, status TEXT, created_at REAL, report_json TEXT
);
"""


class Ingestor:

  def __init__(self, mem, extractor=None, test_calls: bool = True):
    self.mem = mem
    self.extractor = extractor
    self.test_calls = test_calls
    mem.store.executescript(_BATCH_SCHEMA)

  # -------------------------------------------------------------- stage
  async def stage(self, text: str, source: str = "chat") -> dict:
    extractor = self.extractor or (CardExtractor() if CardExtractor.applies(text) else _default_llm())
    context = {"procedures": [p.name for p in self.mem.kg.all()],
               "parameters": [t["canonical"] for t in self.mem.glossary.all("parameter")]}
    ex = Extraction()
    for part in (chunk(text) if not isinstance(extractor, CardExtractor) else [text]):
      got = await extractor.extract(part, context)
      ex.procedures += got.procedures
      ex.terms += got.terms
    warnings: list[str] = []

    # Glossary first, so the new vocabulary canonicalises the procedures.
    staged_aliases: dict[str, str] = {}
    terms = []
    for t in ex.terms:
      kind = t.kind
      canonical = safe_name(t.term) if kind == "parameter" else t.term.strip()
      action = "update" if self.mem.glossary.get(canonical, kind) else "new"
      terms.append(t.model_dump() | {"term": canonical, "action": action})
      if kind == "parameter":
        for a in t.aliases + [t.term]:
          staged_aliases[safe_name(a)] = canonical

    def canon(name: str) -> str:
      key = safe_name(name)
      return staged_aliases.get(key) or self.mem.glossary.canonical_param(key)

    # Canonicalise and dedupe procedures.
    procs: dict[str, dict] = {}
    for d in ex.procedures:
      name = safe_name(d.name)
      rename = {}
      for io in d.inputs + d.outputs:
        c = canon(io)
        if c != io:
          rename[io] = c
      inputs = list(dict.fromkeys(canon(i) for i in d.inputs))
      outputs = list(dict.fromkeys(canon(o) for o in d.outputs))
      call = self._call_spec(d.call, rename)
      if call is None and any(x.relation == "made_of" for x in d.depends_on):
        call = {"kind": "composite"}
      action, target = self._dedupe(name, d.description, inputs, outputs)
      if name in procs:
        warnings.append(f"Duplicate procedure '{name}' in the text; kept the first one.")
        continue
      procs[name] = {
          "name": target or name, "action": action, "description": d.description, "domain": d.domain,
          "inputs": inputs, "outputs": outputs, "steps_md": d.steps_md, "call": call,
          "renamed": rename, "evidence": d.evidence[:200],
          "sample_inputs": {canon(kv.name): kv.value for kv in d.sample_inputs},
          "deps": [x.model_dump() for x in d.depends_on], "call_check": "none"}
    by_final = {p["name"]: p for p in procs.values()}

    edges = self._infer_edges(by_final, canon, warnings)
    for p in by_final.values():
      p["call_check"], p["call"] = await self._check_call(p)
    report = {
        "batch_id": uuid.uuid4().hex[:10], "source": source, "created_at": now(),
        "procedures": [{k: v for k, v in p.items() if k != "deps"} for p in by_final.values()],
        "edges": edges, "terms": terms, "warnings": warnings,
    }
    self.mem.store.execute("INSERT INTO ingest_batches(id, source, status, created_at, report_json) VALUES (?,?,?,?,?)",
                           (report["batch_id"], source, "staged", report["created_at"], json.dumps(report)))
    return report

  def _call_spec(self, call: DraftCall | None, rename: dict[str, str]) -> dict | None:
    if call is None:
      return None

    def fix(s: str) -> str:
      for old, new in rename.items():
        s = s.replace("{" + old + "}", "{" + new + "}")
      return s
    if call.url:
      host = urlparse(call.url).hostname or ""
      return {"kind": "http_json", "source": host, "url": fix(call.url),
              "params": {kv.name: fix(kv.value) for kv in call.params},
              "extract": {rename.get(kv.name, kv.name): fix(kv.value) for kv in call.extract},
              "required": [rename.get(r, r) for r in call.required]}
    if call.expr:
      expr = call.expr
      out = "result"
      if "=" in expr:
        out, expr = [x.strip() for x in expr.split("=", 1)]
      for old, new in rename.items():
        expr = re.sub(rf"\b{re.escape(old)}\b", new, expr)
      return {"kind": "compute", "expr": expr, "output": rename.get(out, out)}
    return None

  def _dedupe(self, name, description, inputs, outputs) -> tuple[str, str | None]:
    if self.mem.kg.get(name):
      return "update", name
    for cand in self.mem.kg.search(f"{name.replace('_', ' ')} {description}", k=3):
      io_a, io_b = set(inputs + outputs), set(cand.inputs + cand.outputs)
      io_sim = len(io_a & io_b) / len(io_a | io_b) if io_a and io_b else 0
      desc_sim = jaccard(description, cand.description)
      if desc_sim >= 0.25 and 0.5 * desc_sim + 0.5 * io_sim >= 0.65:   # same task, same I/O
        return "update", cand.name
    return "new", None

  def _resolve_target(self, target: str, batch: dict, needs: list[str] | None = None) -> str | None:
    """Map a dependency phrase to a procedure: exact name, else best of lexical
    similarity plus a bonus when the candidate produces inputs the source needs."""
    name = safe_name(target)
    if name in batch or self.mem.kg.get(name):
      return name
    needs = set(needs or [])
    pool = {b["name"]: (b["description"], set(b["outputs"])) for b in batch.values()}
    for p in self.mem.kg.search(self.mem.glossary.expand_query(target), k=3):
      pool.setdefault(p.name, (p.description, set(p.outputs)))
    best, best_score = None, 0.0
    for cand, (desc, outputs) in pool.items():
      score = jaccard(self.mem.glossary.expand_query(target), f"{cand.replace('_', ' ')} {desc}")
      score += 0.5 if needs & outputs else 0.0
      if score > best_score:
        best, best_score = cand, score
    return best if best_score >= 0.3 else None

  def _infer_edges(self, batch: dict, canon, warnings: list[str]) -> list[dict]:
    providers: dict[str, list[str]] = defaultdict(list)    # output name -> procedures
    for p in self.mem.kg.all():
      for o in p.outputs:
        providers[o].append(p.name)
    for p in batch.values():
      for o in p["outputs"]:
        providers[o].append(p["name"])

    edges: dict[tuple, dict] = {}
    for p in batch.values():
      src = p["name"]
      for d in p["deps"]:   # signal 1: the text says so
        dst = self._resolve_target(d["target"], {k: v for k, v in batch.items() if k != src}, p["inputs"])
        if not dst or dst == src:
          warnings.append(f"{src}: could not resolve dependency '{d['target']}'")
          continue
        etype = "COMPOSED_OF" if d["relation"] == "made_of" else "DEPENDS_ON"
        mapping = {canon(kv["name"]): canon(kv["value"]) for kv in d["mapping"]}
        edges[(src, dst, etype)] = {"src": src, "dst": dst, "type": etype, "mapping": mapping,
                                    "signals": ["text"], "status": "confirmed"}
      for inp in p["inputs"]:   # signal 2: someone else produces this input
        for dst in providers.get(inp, []):
          if dst == src:
            continue
          key = (src, dst, "DEPENDS_ON")
          if key in edges:
            edges[key]["mapping"].setdefault(inp, inp)
            if "io" not in edges[key]["signals"]:
              edges[key]["signals"].append("io")
          elif (src, dst, "COMPOSED_OF") not in edges:
            edges[key] = {"src": src, "dst": dst, "type": "DEPENDS_ON", "mapping": {inp: inp},
                          "signals": ["io"], "status": "review"}
          else:
            continue
    # A text dependency's mapping may name outputs the target lacks.
    for e in edges.values():
      dst_outputs = set((batch.get(e["dst"]) or {}).get("outputs", [])) or set(
          (self.mem.kg.get(e["dst"]).outputs if self.mem.kg.get(e["dst"]) else []))
      bad = [k for k, v in e["mapping"].items() if dst_outputs and v not in dst_outputs]
      if bad:
        e["warning"] = f"mapping {bad} not produced by {e['dst']}"
      e["reason"] = ("stated in text and inputs match outputs" if e["signals"] == ["text", "io"]
                     else "stated in text" if e["signals"] == ["text"]
                     else f"inputs {sorted(e['mapping'])} match outputs of {e['dst']}; confirm")
    self._mark_cycles(list(edges.values()))
    return list(edges.values())

  def _mark_cycles(self, edges: list[dict]) -> None:
    graph = defaultdict(set)
    for e in self.mem.kg.edges():
      if e["type"] in ("DEPENDS_ON", "COMPOSED_OF"):
        graph[e["src"]].add(e["dst"])

    def reaches(a, b, seen=None):
      seen = seen or set()
      if a == b:
        return True
      seen.add(a)
      return any(reaches(n, b, seen) for n in graph[a] if n not in seen)
    for e in sorted(edges, key=lambda e: e["status"] != "confirmed"):   # confirmed edges win
      if reaches(e["dst"], e["src"]):
        e["status"], e["reason"] = "rejected", "would create a cycle"
      elif e["status"] in ("confirmed", "review"):
        graph[e["src"]].add(e["dst"])

  async def _check_call(self, p: dict) -> tuple[str, dict | None]:
    call = p["call"]
    if not call:
      return "none", None
    if call["kind"] == "composite":
      return "composite", call
    missing = template_vars(call) - set(p["inputs"])
    if missing:
      return f"invalid: uses undeclared inputs {sorted(missing)}", None
    if call["kind"] == "http_json":
      host = urlparse(call["url"]).hostname or ""
      if "*" not in settings.http_allowlist and host not in settings.http_allowlist:
        return f"blocked: add '{host}' to HTTP_ALLOWLIST, then re-ingest", None
    if not self.test_calls:
      return "untested", call
    needed = template_vars(call)
    if not needed <= set(p["sample_inputs"]):
      return f"untested: no sample values for {sorted(needed - set(p['sample_inputs']))}", call
    try:
      from .executor import coerce
      out = await execute_call(call, {k: coerce(v) for k, v in p["sample_inputs"].items()})
      p["sample_output"] = {k: str(v)[:80] for k, v in out.items()}
      return "verified", call
    except Exception as e:  # noqa: BLE001
      return f"failed: {type(e).__name__}: {str(e)[:120]}", None

  # -------------------------------------------------------------- apply
  def get_batch(self, batch_id: str) -> dict:
    rows = self.mem.store.query("SELECT * FROM ingest_batches WHERE id=?", (batch_id,))
    if not rows:
      raise KeyError(f"No staged batch {batch_id}")
    return json.loads(rows[0]["report_json"]) | {"status": rows[0]["status"]}

  def apply(self, batch_id: str, approve: list[str] | Literal["all"] | None = None) -> dict:
    """Write a staged batch. `approve` lists review edges as 'src->dst', or 'all'."""
    report = self.get_batch(batch_id)
    if report["status"] == "applied":
      raise ValueError(f"Batch {batch_id} was already applied")
    kg, glossary = self.mem.kg, self.mem.glossary
    summary = {"terms": 0, "procedures_new": [], "procedures_updated": [], "edges": [], "skipped_edges": []}
    for t in report["terms"]:
      glossary.define(t["term"], t["kind"], t["definition"], t["aliases"], scope=t["applies_to"],
                      links=t["related_procedures"], origin="ingested")
      summary["terms"] += 1
    for p in report["procedures"]:
      old = kg.get(p["name"])
      kg.upsert_procedure(Procedure(
          name=p["name"], description=p["description"], domain=p["domain"], inputs=p["inputs"],
          outputs=p["outputs"], steps_md=p["steps_md"], call=p["call"] or (old.call if old else None),
          status=old.status if old else "candidate", origin=old.origin if old else "ingested"))
      if p["call"] and p["call"]["kind"] == "http_json" and not kg.db.query(
          "SELECT 1 FROM sources WHERE name=?", (p["call"]["source"],)):
        kg.upsert_source(p["call"]["source"], "http_json", p["call"]["url"], f"ingested from {report['source']}")
      if p["call"] and p["call"]["kind"] == "http_json":
        kg.add_edge(p["name"], p["call"]["source"], "USES_SOURCE")
      summary["procedures_updated" if old else "procedures_new"].append(p["name"])
    approved = set(approve) if isinstance(approve, list) else set()
    for e in report["edges"]:
      tag = f"{e['src']}->{e['dst']}"
      ok = e["status"] == "confirmed" or (e["status"] == "review" and (approve == "all" or tag in approved))
      if not ok:
        summary["skipped_edges"].append(f"{tag} ({e['status']})")
        continue
      try:
        kg.add_edge(e["src"], e["dst"], e["type"], e["mapping"])
        summary["edges"].append(f"{tag} [{e['type']}]")
      except ValueError as err:
        summary["skipped_edges"].append(f"{tag} ({err})")
    self.mem.store.execute("UPDATE ingest_batches SET status='applied' WHERE id=?", (batch_id,))
    return summary


def _default_llm():
  if settings.learner_mode != "llm":
    raise RuntimeError("Free-form text needs the LLM extractor (LEARNER_MODE=llm) or procedure cards.")
  return LlmExtractor()


def render_report(r: dict) -> str:
  lines = [f"Batch {r['batch_id']} from {r['source']}:"]
  for p in r["procedures"]:
    lines.append(f"  [{p['action']}] {p['name']}  in={p['inputs']} out={p['outputs']}  call: {p['call_check']}")
    if p.get("renamed"):
      lines.append(f"        renamed via glossary: {p['renamed']}")
  for e in r["edges"]:
    mark = {"confirmed": "✓", "review": "?", "rejected": "✗"}[e["status"]]
    lines.append(f"  {mark} {e['src']} -{e['type']}-> {e['dst']} {e['mapping'] or ''}  ({e['reason']})"
                 + (f"  ⚠ {e['warning']}" if e.get("warning") else ""))
  for t in r["terms"]:
    lines.append(f"  [{t['action']}] term {t['term']} ({t['kind']}) aliases={t['aliases']}")
  lines += [f"  ! {w}" for w in r["warnings"]]
  n_review = sum(e["status"] == "review" for e in r["edges"])
  lines.append(f"{len(r['procedures'])} procedures, {len(r['terms'])} terms, {len(r['edges'])} edges "
               f"({n_review} need confirmation).")
  return "\n".join(lines)
