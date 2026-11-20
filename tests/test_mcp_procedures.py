"""MCP-backed procedures, LLM steps, side effects and approvals (offline: local stdio MCP server)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("AGENT_DATA_DIR", tempfile.mkdtemp(prefix="pa_mcp_"))

import pytest  # noqa: E402
from google.genai import types  # noqa: E402

from procedural_agent.harness import executor, mcp_client  # noqa: E402
from procedural_agent.harness.ingest import Ingestor  # noqa: E402
from procedural_agent.harness.mcp_client import McpRegistry, expand  # noqa: E402
from procedural_agent.memory import agent_memory  # noqa: E402
from procedural_agent.memory.procedural_kg import Procedure  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "notes_mcp.py"

CARDS = """
## Procedure: notes_stats
Description: How many notes there are and the newest title.
Outputs: count, latest
MCP: notes.stats
Required: count

## Procedure: notes_digest
Description: One-line digest of the notes.
Outputs: digest
Needs: notes_stats
LLM: Write one line: there are {count} notes, newest "{latest}".

## Procedure: notes_add_digest
Description: Store the digest as a new note (write).
Inputs: digest
Outputs: added
Needs: notes_digest (digest->digest)
MCP: notes.add_note title="Digest" body={digest}
Side effect: write
"""


@pytest.fixture()
def notes(tmp_path, monkeypatch):
  store = tmp_path / "notes.json"
  store.write_text(json.dumps({"notes": [{"title": "first"}, {"title": "kickoff"}]}))
  monkeypatch.setenv("NOTES_PATH_FOR_TEST", str(store))
  reg = McpRegistry([{"name": "notes", "command": sys.executable, "args": [str(FIXTURE)],
                      "env": {"NOTES_FILE": "${NOTES_PATH_FOR_TEST}"}, "timeout": 60}])
  mcp_client.set_registry(reg)

  async def fake_llm(spec, prompt):
    return prompt.replace("Write one line: ", "")
  monkeypatch.setattr(executor, "llm_text", fake_llm)
  yield store
  mcp_client.set_registry(None)


def test_env_expansion(monkeypatch):
  monkeypatch.setenv("X_TOKEN", "abc")
  assert expand({"h": "Bearer ${X_TOKEN}", "l": ["${X_TOKEN}", 3]}) == {"h": "Bearer abc", "l": ["abc", 3]}


def test_cards_to_mcp_and_llm_procedures_end_to_end(notes):
  mem = agent_memory()

  async def flow():
    ing = Ingestor(mem)
    report = await ing.stage(CARDS, "notes cards")
    checks = {p["name"]: p["call_check"] for p in report["procedures"]}
    assert checks["notes_stats"] == "verified"                       # live call to the local MCP server
    assert checks["notes_digest"] == "llm step"
    assert checks["notes_add_digest"].startswith("write: not test-run")
    ing.apply(report["batch_id"])
    spec = mem.kg.get("notes_add_digest").call
    assert spec == {"kind": "mcp_tool", "server": "notes", "tool": "add_note",
                    "args": {"title": "Digest", "body": "{digest}"}, "required": [], "side_effect": "write"}

    compiled = mem.kg.compile({"steps": [{"id": "main", "procedure": "notes_add_digest", "inputs": []}]})
    assert compiled["levels"] == [["auto_notes_stats"], ["auto_notes_digest"], ["main"]]
    results = await executor.run_plan(mem.kg, compiled, context={"user_id": "srini", "session_id": "s"})
    assert {k: results["auto_notes_stats"]["outputs"][k] for k in ("count", "latest")} == {"count": 2, "latest": "kickoff"}
    assert results["auto_notes_digest"]["outputs"]["digest"] == 'there are 2 notes, newest "kickoff".'
    main = results["main"]
    assert main["status"] == "pending_approval" and not main["ok"]
    code = main["outputs"]["approval_code"]
    assert 'notes.add_note({"title": "Digest", "body": "there are 2 notes' in main["outputs"]["preview"]
    assert len(json.loads(notes.read_text())["notes"]) == 2               # nothing written yet

    with pytest.raises(PermissionError):
      await executor.execute_approved(code, user_id="someone-else")
    out = await executor.execute_approved(code, user_id="srini")
    assert out["ok"] and out["outputs"]["count"] == 3
    with pytest.raises(ValueError):
      await executor.execute_approved(code, user_id="srini")          # one approval, one execution
    await mcp_client.registry().close()
  asyncio.run(flow())
  assert json.loads(notes.read_text())["notes"][-1] == {"title": "Digest", "body": 'there are 2 notes, newest "kickoff".'}
  assert mem.store.query("SELECT success FROM sources WHERE name='mcp:notes'")[0]["success"] >= 1


def test_dependents_wait_for_approval(notes):
  mem = agent_memory()
  mem.kg.upsert_procedure(Procedure(name="notes_after_write", description="x", outputs=["y"],
                                    call={"kind": "compute", "expr": "count + 1", "output": "y"}))
  mem.kg.add_edge("notes_after_write", "notes_add_digest", "DEPENDS_ON")
  compiled = mem.kg.compile({"steps": [{"id": "z", "procedure": "notes_after_write", "inputs": []}]})
  async def go():
    r = await executor.run_plan(mem.kg, compiled, context={"user_id": "srini"})
    await mcp_client.registry().close()
    return r
  results = asyncio.run(go())
  assert results["z"]["status"] == "skipped" and "Waiting for approval" in results["z"]["error"]


def test_approve_tool_requires_the_users_own_words(notes):
  from procedural_agent.harness.tools import approve_action
  mem = agent_memory()
  code = mem.approvals.create("notes_add_digest", "write",
                              {"kind": "mcp_tool", "server": "notes", "tool": "add_note",
                               "args": {"title": "t"}, "prerendered": True}, "add note t", user_id="srini")

  def ctx(text):
    return SimpleNamespace(user_id="srini", user_content=types.Content(role="user", parts=[types.Part(text=text)]))
  async def go():
    denied = await approve_action(code, ctx("yes go ahead"))
    ok = await approve_action(code, ctx(f"approve {code.lower()}"))
    await mcp_client.registry().close()
    return denied, ok
  denied, ok = asyncio.run(go())
  assert denied["ok"] is False and "must contain the code" in denied["error"]
  assert ok["ok"] is True


def test_expired_approval(notes):
  mem = agent_memory()
  code = mem.approvals.create("p", "write", {"kind": "compute", "expr": "1", "prerendered": True}, "s", user_id="u")
  mem.store.execute("UPDATE pending_actions SET created_at = created_at - 100*3600 WHERE code=?", (code,))
  with pytest.raises(ValueError, match="expired"):
    asyncio.run(executor.execute_approved(code, "u"))


def test_unconfigured_server_is_blocked():
  mcp_client.set_registry(McpRegistry([]))
  try:
    r = asyncio.run(Ingestor(agent_memory()).stage("## Procedure: jira_x\nOutputs: a\nMCP: jira.search jql=x\n", "t"))
    assert r["procedures"][0]["call_check"].startswith("blocked: MCP server 'jira'")
  finally:
    mcp_client.set_registry(None)


def test_writes_are_never_learned_into_composites():
  from procedural_agent.harness import nodes
  mem = agent_memory()
  for name, side in (("r1", "read"), ("w1", "write")):
    mem.kg.upsert_procedure(Procedure(name=name, description=name, outputs=["o"],
                                      call={"kind": "compute", "expr": "1", "output": "o", "side_effect": side}))
  state = {"temp:query": "do r1 and w1", "temp:compiled": {"intent": "x", "steps": {
      "a": {"id": "a", "procedure": "r1", "inputs": {}, "depends_on": []},
      "b": {"id": "b", "procedure": "w1", "inputs": {}, "depends_on": []}}, "levels": [["a", "b"]]},
      "temp:results": {"a": {"ok": True, "status": "ok", "outputs": {"o": 1}},
                       "b": {"ok": True, "status": "ok", "outputs": {"o": 1}}},
      "temp:verdicts": [{"ok": True, "score": 1}], "temp:plan": {"steps": []}}
  ctx = SimpleNamespace(state=state)
  asyncio.run(nodes.learn(ctx, None))
  assert "induced" not in state["last_learning"]
