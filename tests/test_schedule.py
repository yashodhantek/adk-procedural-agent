"""Standing approvals for unattended writes, and the mail MCP server (offline)."""

from __future__ import annotations

import asyncio
import dataclasses
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("AGENT_DATA_DIR", tempfile.mkdtemp(prefix="pa_sched_"))

import pytest  # noqa: E402

from procedural_agent.harness import executor, mcp_client, policy  # noqa: E402
from procedural_agent.harness.mcp_client import McpRegistry  # noqa: E402
from procedural_agent.memory import agent_memory  # noqa: E402
from procedural_agent.memory.procedural_kg import Procedure  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FUTURE = (dt.date.today() + dt.timedelta(days=30)).isoformat()
PAST = (dt.date.today() - dt.timedelta(days=1)).isoformat()
MAIL_CALL = {"kind": "mcp_tool", "server": "mail", "tool": "send_email",
             "args": {"to": "srini@yashodhantek.com", "subject": "Signal brief", "markdown": "# hi"}}


# ------------------------------------------------------------------ policy rules
def rule(**kw):
  return dict({"procedure": "email_brief", "args": {"to": ["srini@yashodhantek.com"]}, "until": FUTURE, "_index": 0}, **kw)


def test_policy_allows_only_the_exact_bounds():
  m = policy.match
  assert m("email_brief", "write", MAIL_CALL, "srini", [rule()])
  extra = dict(MAIL_CALL, args=dict(MAIL_CALL["args"], to="srini@yashodhantek.com, someone@else.com"))
  assert m("email_brief", "write", extra, "srini", [rule()]) is None                 # extra recipient
  assert m("email_brief", "destructive", MAIL_CALL, "srini", [rule()]) is None       # never destructive
  assert m("email_brief", "write", MAIL_CALL, "srini", [rule(until=PAST)]) is None   # expired
  assert m("email_brief", "write", MAIL_CALL, "srini", [rule(until="")]) is None     # no expiry: ignored
  assert m("other_proc", "write", MAIL_CALL, "srini", [rule()]) is None              # other procedure
  assert m("email_brief", "write", MAIL_CALL, "mallory", [rule(users=["srini"])]) is None
  assert m("email_brief", "write", MAIL_CALL, "srini", [rule(args={"cc": ["x@y.z"]})]) is None   # arg missing
  assert m("email_brief", "write", dict(MAIL_CALL, args=dict(MAIL_CALL["args"], to="SRINI@yashodhantek.com")),
           "srini", [rule()])                                                         # case-insensitive


def test_policy_file_loading(tmp_path):
  f = tmp_path / "approvals_policy.json"
  f.write_text(json.dumps([rule()]))
  assert policy.load_policies(f)[0]["procedure"] == "email_brief"
  f.write_text("{not json")
  assert policy.load_policies(f) == []
  assert policy.load_policies(tmp_path / "missing.json") == []


# -------------------------------------------- unattended run through a real MCP server
@pytest.fixture()
def mail_server(tmp_path, monkeypatch):
  monkeypatch.setenv("MAIL_OUTBOX_FOR_TEST", str(tmp_path / "outbox"))
  reg = McpRegistry([{"name": "mail", "command": "python", "args": [str(ROOT / "packs/mail/mail_mcp.py")],
                      "env": {"MAIL_DRY_RUN": "1", "MAIL_OUTBOX_DIR": "${MAIL_OUTBOX_FOR_TEST}",
                              "MAIL_FROM": "intel@yashodhantek.com"}, "timeout": 60}])
  mcp_client.set_registry(reg)
  policy_file = tmp_path / "approvals_policy.json"
  monkeypatch.setattr(policy, "settings", dataclasses.replace(policy.settings, approvals_policy_file=str(policy_file)))
  mem = agent_memory()
  mem.kg.upsert_procedure(Procedure(name="email_note", description="email a note", inputs=["to", "body"],
                                    outputs=["sent"], call={
                                        "kind": "mcp_tool", "server": "mail", "tool": "send_email",
                                        "args": {"to": "{to}", "subject": "Signal brief", "markdown": "{body}"},
                                        "side_effect": "write"}))
  yield tmp_path / "outbox", policy_file
  mcp_client.set_registry(None)


def _run(to: str, dry_run: bool = False):
  mem = agent_memory()
  compiled = mem.kg.compile({"steps": [{"id": "main", "procedure": "email_note", "inputs": [
      {"name": "to", "value": to}, {"name": "body", "value": "## Rising\n| a | b |\n|---|---|\n| 1 | 2 |"}]}]})

  async def go():
    r = await executor.run_plan(mem.kg, compiled, context={"user_id": "srini", "no_standing_approvals": dry_run})
    await mcp_client.registry().close()
    return r["main"]
  return asyncio.run(go())


def test_standing_approval_runs_the_write_unattended(mail_server):
  outbox, policy_file = mail_server
  policy_file.write_text(json.dumps([{"procedure": "email_note", "args": {"to": ["srini@yashodhantek.com"]},
                                      "users": ["srini"], "until": FUTURE, "note": "daily brief"}]))
  main = _run("srini@yashodhantek.com")
  assert main["status"] == "ok" and main["outputs"]["approved_by"] == "standing approval #0 (daily brief)"
  assert main["outputs"]["dry_run"] is True
  html = next(outbox.glob("*.html")).read_text()
  assert "<table>" in html and "<h2>Rising</h2>" in html                    # Markdown became HTML
  logged = agent_memory().approvals.get(main["outputs"]["approval_code"])
  assert logged["status"] == "executed" and logged["result"]["approved_by"].startswith("standing approval")
  assert logged["call"]["args"]["to"] == "srini@yashodhantek.com"          # exact arguments are on record


def test_writes_outside_the_rule_still_wait(mail_server):
  outbox, policy_file = mail_server
  policy_file.write_text(json.dumps([{"procedure": "email_note", "args": {"to": ["srini@yashodhantek.com"]},
                                      "until": FUTURE}]))
  assert _run("someone@else.com")["status"] == "pending_approval"
  assert _run("srini@yashodhantek.com", dry_run=True)["status"] == "pending_approval"   # --dry-run ignores rules
  assert not outbox.exists() or not list(outbox.glob("*.html"))


def test_mail_server_rejects_bad_recipients():
  sys.path.insert(0, str(ROOT / "packs/mail"))
  import mail_mcp
  assert mail_mcp.recipients("a@b.co; c@d.io") == ["a@b.co", "c@d.io"]
  with pytest.raises(ValueError):
    mail_mcp.recipients("not-an-address")
