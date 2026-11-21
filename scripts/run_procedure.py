"""Run one procedure (and everything it depends on) without the chat loop.

  python scripts/run_procedure.py techintel_brief
  python scripts/run_procedure.py get_weather_forecast city=Hyderabad --json
  python scripts/run_procedure.py techintel_save_brief --user srini     # parks the write, prints its code
  python scripts/approve.py CODE --user srini                          # then approve it

Useful for cron / launchd schedules and for validating MCP-backed procedures.
Writes are parked for approval like in chat, unless an operator rule in
approvals_policy.json pre-approves that exact procedure and its arguments
(--dry-run ignores those rules, so nothing is ever sent).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from procedural_agent.harness.executor import compact, run_plan  # noqa: E402
from procedural_agent.harness.mcp_client import registry  # noqa: E402
from procedural_agent.harness.nodes import normalize_plan  # noqa: E402
from procedural_agent.memory import agent_memory  # noqa: E402


async def main(a) -> int:
  mem = agent_memory()
  proc = mem.kg.get(a.procedure)
  if proc is None:
    print(f"Procedure '{a.procedure}' is not in the agent's graph.\n"
          f"Ingest its card first, e.g.: python scripts/ingest.py packs/techintel/procedures.md --apply",
          file=sys.stderr)
    return 2
  if not proc.call:
    print(f"Procedure '{a.procedure}' has no executable call (written steps only). If its card uses MCP:, "
          f"check the server is in mcp_servers.json, then re-ingest the card.", file=sys.stderr)
    return 2
  inputs = [{"name": k, "value": v} for k, _, v in (p.partition("=") for p in a.inputs)]
  plan, notes = normalize_plan({"steps": [{"id": "main", "procedure": a.procedure, "inputs": inputs}]},
                               mem.glossary, mem.kg)
  compiled = mem.kg.compile(plan)
  try:
    results = await run_plan(mem.kg, compiled, context={"user_id": a.user, "session_id": "cli",
                                                        "no_standing_approvals": a.dry_run})
  finally:
    await registry().close()
  if a.json:
    print(json.dumps(results, indent=2, default=str))
  else:
    print("levels:", " → ".join("[" + ", ".join(lv) + "]" for lv in compiled["levels"]))
    for n in notes:
      print("normalised:", n)
    for r in results.values():
      detail = r["error"] or json.dumps(compact(r["outputs"], 3, 200), ensure_ascii=False, default=str)
      print(f"  {r['status']:>16}  {r['id']:<34} {r['latency_ms']:>7.0f} ms  {detail[:300]}")
    main = results.get("main", {})
    if main.get("status") == "pending_approval":
      print(f"\nWaiting for approval: {main['outputs']['preview']}\n"
            f"Approve with: python scripts/approve.py {main['outputs']['approval_code']} --user {a.user}")
    elif main.get("ok") and main["outputs"].get("approved_by"):
      print(f"\nExecuted under {main['outputs']['approved_by']} (logged as {main['outputs']['approval_code']}).")
    elif main.get("ok") and len(main["outputs"]) == 1 and isinstance(next(iter(main["outputs"].values())), str):
      print("\n" + next(iter(main["outputs"].values())))
  return 0 if results.get("main", {}).get("status") in ("ok", "pending_approval") else 1


if __name__ == "__main__":
  ap = argparse.ArgumentParser()
  ap.add_argument("procedure")
  ap.add_argument("inputs", nargs="*", help="name=value")
  ap.add_argument("--user", default="local-user")
  ap.add_argument("--json", action="store_true")
  ap.add_argument("--dry-run", action="store_true",
                  help="ignore standing approvals: writes are parked and previewed, never executed")
  sys.exit(asyncio.run(main(ap.parse_args())))
