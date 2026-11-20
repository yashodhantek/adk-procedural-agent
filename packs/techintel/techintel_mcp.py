"""MCP server for the Signal / techintel platform (github.com/yashodhantek/techintel).

Wraps the platform's REST API (/api/v1) as MCP tools so any MCP client, including
this agent's procedures, can read live intelligence: trends, the technology
radar, recommendations, concepts with their research reports, and reports.

Run (stdio, the default):
    TECHINTEL_URL=https://intel.yashodhantek.com \
    TECHINTEL_EMAIL=analyst@... TECHINTEL_PASSWORD=... \
    python packs/techintel/techintel_mcp.py

Run as streamable HTTP instead:
    python packs/techintel/techintel_mcp.py --http --port 8765

Auth: email/password login (JWT, refreshed automatically on 401), or a
pre-issued TECHINTEL_TOKEN. All tools are read-only except `save_brief`, which
writes a Markdown file under TECHINTEL_BRIEF_DIR and is marked destructive=False,
read_only=False so clients can gate it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx

try:  # mcp >= 2
  from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
  from mcp.server.fastmcp import FastMCP as _Server  # type: ignore

BASE = (os.environ.get("TECHINTEL_URL") or "http://localhost:8080").rstrip("/") + "/api/v1"
TIMEOUT = float(os.environ.get("TECHINTEL_TIMEOUT") or "20")
BRIEF_DIR = Path(os.environ.get("TECHINTEL_BRIEF_DIR") or "~/techintel-briefs").expanduser()

mcp = _Server(name="techintel", instructions=(
    "Live AI-technology intelligence from the Signal platform: rising/falling concepts, "
    "the technology radar, adopt/trial recommendations, concept research reports with "
    "evidence, and periodic reports. Scores are 0-100."))

_token: str | None = os.environ.get("TECHINTEL_TOKEN") or None


async def _login(client: httpx.AsyncClient) -> str:
  email, password = os.environ.get("TECHINTEL_EMAIL"), os.environ.get("TECHINTEL_PASSWORD")
  if not (email and password):
    raise RuntimeError("Set TECHINTEL_TOKEN, or TECHINTEL_EMAIL and TECHINTEL_PASSWORD")
  r = await client.post(f"{BASE}/auth/login", json={"email": email, "password": password})
  r.raise_for_status()
  return r.json()["access_token"]


async def _get(path: str, params: dict | None = None) -> Any:
  global _token
  async with httpx.AsyncClient(timeout=TIMEOUT) as client:
    if not _token:
      _token = await _login(client)
    for attempt in (1, 2):
      r = await client.get(f"{BASE}{path}", params={k: v for k, v in (params or {}).items() if v not in (None, "")},
                           headers={"Authorization": f"Bearer {_token}"})
      if r.status_code == 401 and attempt == 1 and not os.environ.get("TECHINTEL_TOKEN"):
        _token = await _login(client)
        continue
      r.raise_for_status()
      return r.json()


def _concept_card(c: dict) -> dict:
  keep = ("name", "slug", "stage", "direction", "trend_score", "impact_score", "maturity_score",
          "growth_30d", "mention_count", "source_count", "novelty", "categories", "summary", "description")
  return {k: c[k] for k in keep if k in c and c[k] not in (None, "", [])}


@mcp.tool(description="Trend overview: top, rising and falling concepts (with 30-day growth), category averages and category shifts.")
async def get_trends(limit: int = 8) -> dict:
  d = await _get("/trends")
  return {"as_of": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
          "top": [_concept_card(c) for c in d.get("top", [])[:limit]],
          "rising": [_concept_card(c) for c in d.get("rising", [])[:limit]],
          "falling": [_concept_card(c) for c in d.get("falling", [])[:limit]],
          "by_category": d.get("by_category", [])[:limit],
          "shifts": d.get("shifts", [])[:limit]}


@mcp.tool(description="The live technology radar: each concept's ring (e.g. established, trending, emerging), quadrant, scores and direction.")
async def get_radar(limit: int = 20) -> dict:
  d = await _get("/radar")
  entries = d.get("entries", [])[:limit]
  rings: dict[str, list[str]] = {}
  for e in entries:
    rings.setdefault(e.get("ring", "?"), []).append(e.get("name"))
  return {"rings": rings, "entries": [{k: e.get(k) for k in ("name", "slug", "ring", "quadrant", "trend_score",
                                                               "impact_score", "maturity_score", "direction")}
                                      for e in entries]}


@mcp.tool(description="Adopt / trial / assess / hold recommendations with rationale and a suggested experiment.")
async def get_recommendations(limit: int = 8) -> dict:
  d = await _get("/recommendations")
  return {"generated_at": d.get("generated_at"),
          "items": [{k: i.get(k) for k in ("name", "action", "priority", "rationale", "experiment")}
                    for i in d.get("items", [])[:limit]]}


@mcp.tool(description="List concepts. sort: -trend_score | -impact_score | -created_at. stage: emerging|trending|established|… (optional).")
async def list_concepts(sort: str = "-trend_score", limit: int = 10, stage: str = "") -> dict:
  d = await _get("/concepts", {"sort": sort, "limit": limit, "stage": stage})
  items = [_concept_card(c) for c in d.get("items", [])]
  return {"total": d.get("total"), "items": items, "top_slug": items[0]["slug"] if items else None}


@mcp.tool(description="Full technical detail for one concept (slug or id): definition, scores and signals, timeline, related concepts, and its research report sections with evidence.")
async def get_concept(slug: str) -> dict:
  c = await _get(f"/concepts/{slug}")
  report = c.get("report") or {}
  metrics = (c.get("latest_metrics") or [{}])[0]
  return {
      **_concept_card(c),
      "technical_definition": c.get("technical_definition") or None,
      "domain": c.get("domain_name"),
      "origin": {"date": c.get("origin_date"), "title": c.get("origin_title"), "publisher": c.get("origin_publisher"),
                 "url": c.get("origin_url")},
      "popularization_date": c.get("popularization_date"),
      "signals": {k: metrics.get(k) for k in ("mentions", "prev_mentions", "growth_rate", "research_signal",
                                              "github_signal", "avg_credibility", "score") if k in metrics},
      "related": [{"name": r.get("name"), "type": r.get("type"), "stage": r.get("stage")}
                  for r in (c.get("relationships") or [])[:8]],
      "report": {
          "title": report.get("title"), "confidence": report.get("confidence"),
          "review_status": report.get("review_status"),
          "sections": [{"title": s.get("title") or s.get("heading"),
                        "claims": [{"text": i.get("text"), "type": i.get("type"), "citations": i.get("citations")}
                                   for i in (s.get("items") or [])[:6]]}
                       for s in (report.get("sections") or [])][:10],
          "evidence": [{"ref": e.get("ref_key"), "title": e.get("title"), "publisher": e.get("publisher"),
                        "published_at": e.get("published_at"), "url": e.get("url")}
                       for e in (report.get("evidence") or [])[:8]],
      } if report else None,
  }


@mcp.tool(description="Latest generated reports (research breakthroughs, enterprise impact, comparisons…), newest first.")
async def list_reports(limit: int = 5) -> dict:
  d = await _get("/reports", {"limit": limit})
  return {"items": [{k: i.get(k) for k in ("title", "type", "summary", "period_start", "period_end", "id")}
                    for i in d.get("items", [])]}


@mcp.tool(description="Keyword / semantic search across concepts and content.")
async def search(q: str, limit: int = 8) -> dict:
  return await _get("/search", {"q": q, "limit": limit})


@mcp.tool(description="WRITE: save a Markdown brief to TECHINTEL_BRIEF_DIR and return its path. Requires user approval in the agent.")
async def save_brief(markdown: str, title: str = "techintel-brief") -> dict:
  BRIEF_DIR.mkdir(parents=True, exist_ok=True)
  slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60] or "brief"
  path = BRIEF_DIR / f"{dt.date.today().isoformat()}-{slug}.md"
  path.write_text(markdown, encoding="utf-8")
  return {"saved": str(path), "bytes": len(markdown.encode())}


if __name__ == "__main__":
  ap = argparse.ArgumentParser()
  ap.add_argument("--http", action="store_true")
  ap.add_argument("--port", type=int, default=8765)
  a = ap.parse_args()
  if a.http:
    mcp.run("streamable-http", port=a.port)
  else:
    mcp.run("stdio")
