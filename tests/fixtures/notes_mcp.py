"""Tiny local MCP server used by the tests: a notes store with read and write tools."""

import json
import os
import sys
from pathlib import Path

try:
  from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # mcp 1.x
  from mcp.server.fastmcp import FastMCP as _Server  # type: ignore

STORE = Path(os.environ.get("NOTES_FILE", "notes.json"))
mcp = _Server(name="notes")


def _load() -> dict:
  return json.loads(STORE.read_text()) if STORE.exists() else {"notes": []}


@mcp.tool(description="Count notes and return the newest title.")
def stats() -> dict:
  notes = _load()["notes"]
  return {"count": len(notes), "latest": notes[-1]["title"] if notes else None, "server_pid": os.getpid()}


@mcp.tool(description="Add a note (write).")
def add_note(title: str, body: str = "") -> dict:
  data = _load()
  data["notes"].append({"title": title, "body": body})
  STORE.write_text(json.dumps(data))
  return {"added": title, "count": len(data["notes"])}


if __name__ == "__main__":
  mcp.run("stdio")
