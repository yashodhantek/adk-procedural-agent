"""MCP servers as procedure data sources.

One registry, configured from MCP_SERVERS / MCP_SERVERS_FILE, serves both:
  * procedure steps with `{"kind": "mcp_tool", "server": ..., "tool": ...}` (executor), and
  * the synthesizer's McpToolsets (tools.py).

Local servers run as subprocesses over stdio; remote ones use streamable HTTP.
Sessions are pooled per server by ADK's MCPSessionManager and reused across
steps and turns.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

from ..config import settings

log = logging.getLogger(__name__)
_ENV = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def expand(value: Any) -> Any:
  """Expand ${VAR} from the environment inside strings, lists and dicts."""
  if isinstance(value, str):
    return _ENV.sub(lambda m: os.environ.get(m.group(1), ""), value)
  if isinstance(value, list):
    return [expand(v) for v in value]
  if isinstance(value, dict):
    return {k: expand(v) for k, v in value.items()}
  return value


def connection_params(server: dict):
  from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams, StreamableHTTPConnectionParams
  server = expand(server)
  if server.get("command"):
    from mcp import StdioServerParameters
    return StdioConnectionParams(
        server_params=StdioServerParameters(command=server["command"], args=server.get("args", []),
                                            env={**os.environ, **server.get("env", {})},
                                            cwd=server.get("cwd")),
        timeout=float(server.get("timeout", 30)))
  if server.get("url"):
    return StreamableHTTPConnectionParams(url=server["url"], headers=server.get("headers", {}),
                                          timeout=float(server.get("timeout", 30)))
  raise ValueError(f"MCP server {server.get('name')!r} needs 'command' or 'url'")


def parse_result(result: Any) -> Any:
  """CallToolResult -> structured content, else JSON text, else plain text."""
  if getattr(result, "is_error", False) or getattr(result, "isError", False):
    texts = [getattr(c, "text", "") for c in getattr(result, "content", []) or []]
    raise RuntimeError("MCP tool error: " + " ".join(t for t in texts if t)[:500])
  structured = getattr(result, "structured_content", None) or getattr(result, "structuredContent", None)
  if structured:
    return structured.get("result", structured) if isinstance(structured, dict) and list(structured) == ["result"] else structured
  texts = [getattr(c, "text", None) for c in getattr(result, "content", []) or []]
  texts = [t for t in texts if t]
  if len(texts) == 1:
    try:
      return json.loads(texts[0])
    except json.JSONDecodeError:
      return texts[0]
  return texts


class McpRegistry:

  def __init__(self, servers: list[dict]):
    self.servers = {s["name"]: s for s in servers if s.get("name")}
    self._managers: dict[str, Any] = {}

  def configured(self, name: str) -> bool:
    return name in self.servers

  def _manager(self, name: str):
    if name not in self.servers:
      raise KeyError(f"MCP server '{name}' is not configured (MCP_SERVERS / MCP_SERVERS_FILE)")
    if name not in self._managers:
      from google.adk.tools.mcp_tool.mcp_session_manager import MCPSessionManager
      self._managers[name] = MCPSessionManager(connection_params(self.servers[name]))
    return self._managers[name]

  async def call(self, server: str, tool: str, args: dict | None = None) -> Any:
    session = await self._manager(server).create_session()
    return parse_result(await session.call_tool(tool, args or {}))

  async def list_tools(self, server: str) -> list[dict]:
    session = await self._manager(server).create_session()
    res = await session.list_tools()
    return [{"name": t.name, "description": t.description} for t in res.tools]

  async def close(self) -> None:
    for m in self._managers.values():
      try:
        await m.close()
      except Exception as e:  # noqa: BLE001
        log.debug("MCP close: %s", e)
    self._managers.clear()


_registry: McpRegistry | None = None


def registry() -> McpRegistry:
  global _registry
  if _registry is None:
    _registry = McpRegistry(settings.mcp_servers)
  return _registry


def set_registry(reg: McpRegistry | None) -> None:
  """Tests and scripts can swap the registry (e.g. a fake one)."""
  global _registry
  _registry = reg
