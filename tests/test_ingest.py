"""Glossary and natural-language ingestion tests (offline)."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("AGENT_DATA_DIR", tempfile.mkdtemp(prefix="pa_ing_"))

import httpx  # noqa: E402
import pytest  # noqa: E402

from fakes import mock_transport  # noqa: E402
from procedural_agent.harness import executor  # noqa: E402
from procedural_agent.harness.ingest import (DraftDependency, DraftProcedure, Extraction, Ingestor,  # noqa: E402
                                             KV, render_report)
from procedural_agent.harness.nodes import normalize_plan  # noqa: E402
from procedural_agent.memory import Glossary, ProceduralKG, ReflectionMemory, SemanticMemory  # noqa: E402
from procedural_agent.memory.store import SqliteStore  # noqa: E402

CARDS = (Path(__file__).resolve().parent.parent / "examples" / "sop_travel_cards.md").read_text()


@pytest.fixture()
def mem():
  store = SqliteStore(":memory:")
  return SimpleNamespace(store=store, kg=ProceduralKG(store), facts=SemanticMemory(store),
                         reflections=ReflectionMemory(store), glossary=Glossary(store))


@pytest.fixture(autouse=True)
def apis():
  base = mock_transport()

  def handler(req):
    if req.url.host == "api.open-meteo.com" and "uv_index_max" in str(req.url):
      return httpx.Response(200, json={"daily": {"uv_index_max": [9.1]}})
    return base.handler(req)
  executor.fetcher.transport = httpx.MockTransport(handler)


# ------------------------------------------------------------------ glossary
def test_glossary_resolution_and_normalisation(mem):
  g = mem.glossary
  found = {t["canonical"] for t in g.resolve("convert 50 dollars to rupees, and is Bangalore ok for a jog?")}
  assert {"USD", "INR", "Bengaluru", "good day outside"} <= found
  assert "to_currency" not in found                       # parameter words are ignored in prose
  assert g.canonical_param("lng") == "longitude"
  assert g.normalize_value("to_currency", "₹") == "INR"
  assert g.normalize_value("vs_currency", "rupees") == "inr"   # parameter format: lower
  plan, notes = normalize_plan({"steps": [{"id": "s", "procedure": "convert_amount", "inputs": [
      {"name": "base", "value": "dollars"}, {"name": "to_currency", "value": "rupees"},
      {"name": "amount", "value": "50"}]}]}, g, mem.kg)
  assert {i["name"]: i["value"] for i in plan["steps"][0]["inputs"]} == {
      "from_currency": "USD", "to_currency": "INR", "amount": "50"}
  assert len(notes) == 2
  assert "get air quality" in g.expand_query("how bad is the smog")


def test_user_defined_term_merges(mem):
  g = mem.glossary
  g.define("INR", "value", aliases=["lakh rupees"], scope=["amount_currency"])
  t = g.get("INR", "value")
  assert "amount_currency" in t["scope"] and "to_currency" in t["scope"] and "rupees" in t["aliases"]


# ----------------------------------------------------------------- ingestion
def test_cards_pipeline_end_to_end(mem):
  ing = Ingestor(mem)
  r = asyncio.run(ing.stage(CARDS, "sop_travel_cards.md"))
  procs = {p["name"]: p for p in r["procedures"]}
  uv = procs["get_uv_index"]
  assert uv["inputs"] == ["latitude", "longitude"]        # lat_deg / lng canonicalised via glossary
  assert uv["call"]["params"]["latitude"] == "{latitude}"  # template rewritten too
  assert uv["call_check"] == "verified" and uv["sample_output"]["uv_index_max"] == "9.1"
  assert procs["beach_day_check"]["call"] == {"kind": "composite"}
  edges = {(e["src"], e["dst"]): e for e in r["edges"]}
  assert edges[("get_uv_index", "geocode_city")]["status"] == "confirmed"
  assert edges[("get_uv_index", "geocode_city")]["signals"] == ["text", "io"]
  assert edges[("travel_budget_in_inr", "get_fx_rate")]["status"] == "review"   # I/O match only
  assert "need confirmation" in render_report(r)

  # Staged only: nothing in the graph yet
  assert mem.kg.get("get_uv_index") is None
  s = ing.apply(r["batch_id"])                               # no approvals
  assert "travel_budget_in_inr->get_fx_rate (review)" in s["skipped_edges"]
  assert mem.kg.get("get_uv_index").status == "candidate"
  assert mem.kg.dependencies("get_uv_index") == ["geocode_city"]
  assert mem.glossary.canonical_param("lat_degrees") == "latitude"
  assert "get_uv_index" in mem.glossary.get("UV index", "concept")["procedures"]
  with pytest.raises(ValueError):
    ing.apply(r["batch_id"])                                 # batches apply once

  c = mem.kg.compile({"steps": [{"id": "b", "procedure": "beach_day_check", "inputs": [{"name": "city", "value": "Goa"}]}]})
  results = asyncio.run(executor.run_plan(mem.kg, c))
  assert results["b"]["ok"] and results["b"]["outputs"]["uv_index_max"] == 9.1 and results["b"]["outputs"]["us_aqi"] == 62


class StubLlm:
  """Stands in for LlmExtractor: what Gemini returns for a free-form paragraph."""

  def __init__(self, ex: Extraction):
    self.ex = ex

  async def extract(self, text, context=None):
    return self.ex


def test_free_text_resolution_dedupe_and_cycles(mem):
  ex = Extraction(procedures=[
      DraftProcedure(  # dependency described in words, not by name
          name="Get Sunrise Time", description="Sunrise and sunset for a city", inputs=["lat", "lon"],
          outputs=["sunrise", "sunset"],
          depends_on=[DraftDependency(target="look up the coordinates of the city")]),
      DraftProcedure(  # same task as an existing procedure -> update, not a duplicate
          name="fetch exchange rate", description="Latest exchange rate between two currencies",
          inputs=["from_currency", "to_currency"], outputs=["rate", "date"]),
      DraftProcedure(  # would make geocode depend on its own dependent
          name="geocode_city", description="Resolve a city or place name to latitude, longitude",
          inputs=["city"], outputs=["latitude", "longitude"],
          depends_on=[DraftDependency(target="get_weather_forecast")]),
      DraftProcedure(name="ghost", description="x", depends_on=[DraftDependency(target="quantum flux reader")]),
  ])
  r = asyncio.run(Ingestor(mem, extractor=StubLlm(ex)).stage("free text", "notes"))
  procs = {p["name"]: p for p in r["procedures"]}
  assert procs["get_sunrise_time"]["inputs"] == ["latitude", "longitude"]
  assert procs["get_fx_rate"]["action"] == "update"
  edges = {(e["src"], e["dst"]): e for e in r["edges"]}
  assert edges[("get_sunrise_time", "geocode_city")]["status"] == "confirmed"
  assert edges[("geocode_city", "get_weather_forecast")]["status"] == "rejected"
  assert any("quantum flux" in w for w in r["warnings"])


def test_blocked_host_and_undeclared_inputs(mem):
  r = asyncio.run(Ingestor(mem).stage(
      "## Procedure: get_stock_price\nInputs: ticker\nOutputs: price\n"
      "API: GET https://finance.example.com/quote?symbol={ticker}\nExtract: price=price\n\n"
      "## Procedure: bad_math\nInputs: a\nOutputs: c\nCompute: c = a * b\n", "x"))
  checks = {p["name"]: p["call_check"] for p in r["procedures"]}
  assert checks["get_stock_price"].startswith("blocked") and checks["bad_math"].startswith("invalid")
