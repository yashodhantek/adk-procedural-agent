"""Unit tests for the procedural knowledge graph, executor and memory stores."""

from __future__ import annotations

import asyncio
import os
import tempfile

os.environ.setdefault("AGENT_DATA_DIR", tempfile.mkdtemp(prefix="pa_unit_"))

import pytest  # noqa: E402

from procedural_agent.harness import executor  # noqa: E402
from procedural_agent.harness.executor import extract, run_plan, safe_eval  # noqa: E402
from procedural_agent.memory.procedural_kg import ProceduralKG  # noqa: E402
from procedural_agent.memory.reflection import ReflectionMemory  # noqa: E402
from procedural_agent.memory.semantic import SemanticMemory  # noqa: E402
from procedural_agent.memory.store import SqliteStore  # noqa: E402
from fakes import mock_transport  # noqa: E402


@pytest.fixture()
def kg():
  return ProceduralKG(SqliteStore(":memory:"))


def test_dependency_closure_and_parallel_levels(kg):
  c = kg.compile({"steps": [
      {"id": "w", "procedure": "get_weather_forecast", "inputs": [{"name": "city", "value": "Pune"}]},
      {"id": "q", "procedure": "get_air_quality", "inputs": [{"name": "city", "value": "Pune"}]},
      {"id": "fx", "procedure": "get_fx_rate", "inputs": []}]})
  assert c["levels"][0] == ["auto_geocode_city", "fx"]          # independent roots run together
  assert sorted(c["levels"][1]) == ["q", "w"]                     # both wait for one shared geocode
  assert c["added"] == ["auto_geocode_city"]


def test_composite_expansion_and_unknown(kg):
  c = kg.compile({"steps": [{"id": "b", "procedure": "city_conditions_brief", "inputs": [{"name": "city", "value": "Goa"}]},
                            {"id": "x", "procedure": "does_not_exist"}]})
  assert c["steps"]["x"]["procedure"] == "adhoc" and c["warnings"]
  assert c["levels"][-1] == ["b"] and len(c["levels"]) == 3


def test_cycle_rejected(kg):
  with pytest.raises(ValueError):
    kg.add_edge("geocode_city", "get_weather_forecast", "DEPENDS_ON")
  with pytest.raises(ValueError):
    kg.compile({"steps": [{"id": "a", "procedure": "adhoc", "depends_on": ["b"]},
                          {"id": "b", "procedure": "adhoc", "depends_on": ["a"]}]})


def test_extract_and_safe_eval():
  data = {"results": [{"lat": 1.5}], "features": [{"properties": {"mag": 4}}, {"properties": {"mag": 5}}]}
  assert extract(data, "results.0.lat") == 1.5
  assert extract(data, "features[*].properties.mag") == [4, 5]
  assert safe_eval("round(amount * rate, 2)", {"amount": 3, "rate": 1.2345}) == 3.7
  with pytest.raises(Exception):
    safe_eval("__import__('os')", {})


def test_failed_source_skips_dependents_and_lowers_reliability(kg):
  executor.fetcher.transport = mock_transport(fail_hosts=("geocoding-api.open-meteo.com",))
  c = kg.compile({"steps": [{"id": "w", "procedure": "get_weather_forecast", "inputs": [{"name": "city", "value": "X"}]},
                            {"id": "fx", "procedure": "convert_amount", "inputs": [
                                {"name": "amount", "value": "10"}, {"name": "from_currency", "value": "EUR"},
                                {"name": "to_currency", "value": "INR"}]}]})
  r = asyncio.run(run_plan(kg, c))
  assert r["auto_geocode_city"]["status"] == "failed" and r["w"]["status"] == "skipped"
  assert r["fx"]["outputs"]["converted"] == 840.0                 # the independent branch still succeeds
  assert kg.get("geocode_city").reliability < 0.5


def test_search_prefers_reliable(kg):
  assert kg.search("exchange rate dollars to rupees")[0].name in ("get_fx_rate", "convert_amount")


def test_semantic_supersede_and_reflection_dedupe():
  store = SqliteStore(":memory:")
  facts, refl = SemanticMemory(store), ReflectionMemory(store)
  facts.remember("u", "currency", "Prefers prices in INR", "preference")
  facts.remember("u", "currency", "Prefers prices in INR and USD", "preference")
  assert len(facts.search("u", "currency")) == 1
  a = refl.add_lesson("fx", "Always give the FX rate date.")
  b = refl.add_lesson("fx", "Always give the FX rate date!")
  assert a == b
  ids = [x["id"] for x in refl.playbook()]
  for _ in range(3):
    refl.score_bullets(ids[:1], helpful=False)
  assert refl.prune() == 1
