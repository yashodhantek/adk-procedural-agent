"""Deterministic DAG executor for compiled procedure plans.

Each plan level runs in parallel (asyncio.gather, bounded by a semaphore);
outputs flow along DEPENDS_ON edges using the edge's input/output mapping.
Every run updates procedure and source reliability in the knowledge graph,
which is what lets the planner learn which recipes and sources to trust.
"""

from __future__ import annotations

import ast
import asyncio
import json
import operator
import re
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from ..config import settings
from ..memory.procedural_kg import ProceduralKG

_VAR = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")


# ----------------------------------------------------------------- templating
def render(template: Any, variables: dict[str, Any]) -> Any:
  if not isinstance(template, str):
    return template
  whole = _VAR.fullmatch(template)
  if whole:
    if whole.group(1) not in variables:
      raise KeyError(whole.group(1))
    return variables[whole.group(1)]

  def sub(m):
    if m.group(1) not in variables:
      raise KeyError(m.group(1))
    return str(variables[m.group(1)])
  return _VAR.sub(sub, template)


def extract(data: Any, path: str) -> Any:
  """Tiny path language: a.b.0.c  and  list[*].field  (maps over a list)."""
  cur = data
  parts = [p for p in path.split(".") if p]
  for i, part in enumerate(parts):
    if part.endswith("[*]"):
      key = part[:-3]
      seq = cur.get(key, []) if isinstance(cur, dict) else []
      rest = ".".join(parts[i + 1:])
      return [extract(item, rest) if rest else item for item in seq]
    if isinstance(cur, list):
      try:
        cur = cur[int(part)]
      except (ValueError, IndexError):
        return None
    elif isinstance(cur, dict):
      cur = cur.get(part, cur.get(part.lower(), cur.get(part.upper())))
    else:
      return None
    if cur is None:
      return None
  return cur


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg,
        ast.Mod: operator.mod}
_FUNCS = {"round": round, "min": min, "max": max, "abs": abs, "float": float}


def safe_eval(expr: str, variables: dict[str, Any]) -> Any:
  def ev(node):
    if isinstance(node, ast.Expression):
      return ev(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
      return node.value
    if isinstance(node, ast.Name):
      return float(variables[node.id])
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
      return _OPS[type(node.op)](ev(node.left), ev(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
      return _OPS[type(node.op)](ev(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _FUNCS:
      return _FUNCS[node.func.id](*[ev(a) for a in node.args])
    raise ValueError(f"Unsupported expression element: {ast.dump(node)[:60]}")
  return ev(ast.parse(expr, mode="eval"))


def coerce(value: Any) -> Any:
  if isinstance(value, str):
    v = value.strip()
    if re.fullmatch(r"-?\d+", v):
      return int(v)
    if re.fullmatch(r"-?\d*\.\d+", v):
      return float(v)
    return v
  return value


# ----------------------------------------------------------------------- HTTP
class HttpFetcher:
  """Allow-listed JSON GET with timeout and retry. Swap `transport` in tests."""

  def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
    self.transport = transport

  def check(self, url: str) -> None:
    host = urlparse(url).hostname or ""
    if "*" not in settings.http_allowlist and host not in settings.http_allowlist:
      raise PermissionError(f"Host '{host}' is not in HTTP_ALLOWLIST")

  async def get_json(self, url: str, params: dict | None = None, retries: int = 2) -> Any:
    return await self.request_json("GET", url, params=params, retries=retries)

  async def request_json(self, method: str, url: str, *, params: dict | None = None, json: Any = None,
                         headers: dict | None = None, check: bool = True, retries: int = 2) -> Any:
    """`check=False` is for fixed vendor endpoints chosen by the operator (search APIs)."""
    if check:
      self.check(url)
    last: Exception | None = None
    async with httpx.AsyncClient(timeout=settings.step_timeout_s, transport=self.transport,
                                 headers={"User-Agent": "adk-procedural-agent/1.0"}) as client:
      for attempt in range(retries + 1):
        try:
          resp = await client.request(method, url, params=params, json=json, headers=headers)
          if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            await asyncio.sleep(0.5 * 2 ** attempt)
            continue
          resp.raise_for_status()
          return resp.json()
        except (httpx.TransportError, httpx.HTTPStatusError, ValueError) as e:
          last = e
          if attempt < retries:
            await asyncio.sleep(0.5 * 2 ** attempt)
    raise RuntimeError(f"{method} {url} failed: {last}")


fetcher = HttpFetcher()


# ------------------------------------------------------------------ execution
def _step_vars(kg: ProceduralKG, step: dict, results: dict[str, dict]) -> dict[str, Any]:
  variables = {k: coerce(v) for k, v in step.get("inputs", {}).items()}
  proc = step["procedure"]
  for dep_id in step.get("depends_on", []):
    dep = results.get(dep_id) or {}
    outputs = dep.get("outputs") or {}
    edge = next((e for e in kg.edges(src=proc, dst=dep.get("procedure"), type_="DEPENDS_ON")), None)
    if edge and edge["mapping"]:
      for my_in, their_out in edge["mapping"].items():
        if their_out in outputs:
          variables[my_in] = outputs[their_out]
    else:
      for k, v in outputs.items():
        variables.setdefault(k, v)
  return variables


async def run_step(kg: ProceduralKG, step: dict, results: dict[str, dict]) -> dict:
  started = time.perf_counter()
  proc_name = step["procedure"]
  out = {"id": step["id"], "procedure": proc_name, "ok": False, "status": "failed",
         "outputs": {}, "error": None, "source": None, "latency_ms": 0.0}
  if proc_name == "adhoc":
    out.update(status="deferred", error="No executable procedure; handled by the synthesizer.")
    return out
  proc = kg.get(proc_name)
  if proc is None or not proc.call:
    out.update(status="deferred", error="Procedure has written steps only; follow its skill.")
    return out
  failed_deps = [d for d in step.get("depends_on", []) if not (results.get(d) or {}).get("ok")]
  if failed_deps:
    out.update(status="skipped", error=f"Upstream steps failed: {failed_deps}")
    return out

  call = proc.call
  variables = _step_vars(kg, step, results)
  out["source"] = call.get("source")
  try:
    upstream = [(results.get(d) or {}).get("outputs") or {} for d in step.get("depends_on", [])]
    out.update(ok=True, status="ok", outputs=await execute_call(call, variables, upstream))
  except KeyError as e:
    out["error"] = f"Missing input {e.args[0]!r} for {proc_name}"
  except Exception as e:  # noqa: BLE001 - every failure is data for learning
    out["error"] = f"{type(e).__name__}: {e}"
  out["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
  return out


async def execute_call(call: dict, variables: dict[str, Any], upstream: list[dict] | None = None) -> dict:
  """Run one call spec. Raises KeyError for a missing input, other errors on failure."""
  kind = call.get("kind")
  if kind == "http_json":
    url = render(call["url"], variables)
    params = {k: render(v, variables) for k, v in call.get("params", {}).items()}
    data = await asyncio.wait_for(fetcher.get_json(url, params), timeout=settings.step_timeout_s * 3)
    outputs = {name: extract(data, render(path, variables)) for name, path in call.get("extract", {}).items()}
  elif kind == "compute":
    outputs = {call.get("output", "result"): safe_eval(call["expr"], variables)}
  elif kind == "composite":
    outputs = {}
    for u in upstream or []:
      outputs.update(u)
  else:
    raise ValueError(f"Unknown call kind {kind}")
  missing = [r for r in call.get("required", []) if outputs.get(r) in (None, [], "")]
  if missing:
    raise ValueError(f"Source returned no value for {missing}")
  return outputs


def template_vars(call: dict) -> set[str]:
  """Input names a call spec needs ({var} in url, params and extract paths, names in expr)."""
  found: set[str] = set()
  for text in [call.get("url", "")] + list(call.get("params", {}).values()) + list(call.get("extract", {}).values()):
    found |= set(_VAR.findall(str(text)))
  if call.get("kind") == "compute" and call.get("expr"):
    found |= {n.id for n in ast.walk(ast.parse(call["expr"], mode="eval"))
              if isinstance(n, ast.Name) and n.id not in _FUNCS}
  return found


async def run_plan(kg: ProceduralKG, compiled: dict, record: bool = True) -> dict[str, dict]:
  results: dict[str, dict] = {}
  sem = asyncio.Semaphore(settings.max_parallel_steps)

  async def guarded(step):
    async with sem:
      return await run_step(kg, step, results)

  for level in compiled["levels"]:
    outs = await asyncio.gather(*(guarded(compiled["steps"][sid]) for sid in level))
    for o in outs:
      results[o["id"]] = o
      if record and o["status"] in ("ok", "failed"):
        kg.record_outcome(o["procedure"], o["ok"], o["latency_ms"])
        if o["source"]:
          kg.record_source_outcome(o["source"], o["ok"], o["latency_ms"])
  return results


def compact(value: Any, max_items: int = 5, max_str: int = 400) -> Any:
  """Shrink results before they go into a prompt (full data goes to artifacts)."""
  if isinstance(value, dict):
    return {k: compact(v, max_items, max_str) for k, v in value.items()}
  if isinstance(value, list):
    head = [compact(v, max_items, max_str) for v in value[:max_items]]
    return head + ([f"... {len(value) - max_items} more"] if len(value) > max_items else [])
  if isinstance(value, str) and len(value) > max_str:
    return value[:max_str] + "..."
  return value
