"""Approve or reject actions parked by procedures with side effects.

  python scripts/approve.py --list [--user ID]
  python scripts/approve.py CODE [--user ID]
  python scripts/approve.py CODE --reject
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

from procedural_agent.harness.executor import execute_approved  # noqa: E402
from procedural_agent.harness.mcp_client import registry  # noqa: E402
from procedural_agent.memory import agent_memory  # noqa: E402


async def main(a) -> int:
  approvals = agent_memory().approvals
  if a.list or not a.code:
    for p in approvals.pending(a.user):
      print(f"{p['code']}  [{p['side_effect']}]  {p['summary']}")
    return 0
  if a.reject:
    approvals.decide(a.code, "rejected")
    print(f"Rejected {a.code}")
    return 0
  a_ = approvals.get(a.code)
  if a_:
    print(f"Running: {a_['summary']}")
  try:
    out = await execute_approved(a.code, a.user)
  except (KeyError, ValueError, PermissionError) as e:
    print(e)
    return 1
  finally:
    await registry().close()
  print(json.dumps(out, indent=2, default=str))
  return 0 if out.get("ok") else 1


if __name__ == "__main__":
  ap = argparse.ArgumentParser()
  ap.add_argument("code", nargs="?")
  ap.add_argument("--user")
  ap.add_argument("--list", action="store_true")
  ap.add_argument("--reject", action="store_true")
  sys.exit(asyncio.run(main(ap.parse_args())))
