"""Interactive chat with persistent sessions, episodic memory and artifacts.

  python scripts/run_cli.py --user srini            # new session
  python scripts/run_cli.py --user srini --session my-trip   # resume one
Type /graph to print the procedure graph, /learned for the last learning report.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from google.adk import Runner  # noqa: E402
from google.genai import types  # noqa: E402

from procedural_agent.agent import app  # noqa: E402
from procedural_agent.memory import agent_memory, build_services  # noqa: E402


async def main(user: str, session: str) -> None:
  sessions, memory, artifacts = build_services()
  runner = Runner(app=app, session_service=sessions, memory_service=memory,
                  artifact_service=artifacts, auto_create_session=True)
  print(f"session {session} — Ctrl-D to quit")
  while True:
    try:
      text = input("\nyou> ").strip()
    except EOFError:
      break
    if not text:
      continue
    if text == "/graph":
      print(agent_memory().kg.to_mermaid())
      continue
    if text == "/learned":
      s = await sessions.get_session(app_name=app.name, user_id=user, session_id=session)
      print(s.state.get("last_learning") if s else "nothing yet")
      continue
    async for ev in runner.run_async(user_id=user, session_id=session,
                                     new_message=types.Content(role="user", parts=[types.Part(text=text)])):
      if ev.content and ev.content.parts:
        for p in ev.content.parts:
          if p.function_call:
            print(f"  · {ev.author} → {p.function_call.name}")
          elif p.text and ev.author == app.name:
            print(f"\nagent> {p.text}")
  await runner.close()


if __name__ == "__main__":
  ap = argparse.ArgumentParser()
  ap.add_argument("--user", default="local-user")
  ap.add_argument("--session", default=f"s-{uuid.uuid4().hex[:8]}")
  a = ap.parse_args()
  asyncio.run(main(a.user, a.session))
