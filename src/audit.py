"""Audit log: one JSON line per tool call, written by FastMCP middleware."""

import json
from datetime import datetime, timezone
from pathlib import Path

from fastmcp.server.middleware import Middleware


class AuditLog(Middleware):
    """Record every tool call: timestamp, tool, arguments and response.

    Middleware wraps the server's handling of each MCP request. FastMCP calls
    on_call_tool for every tools/call; `call_next` runs the actual tool.
    The response logged is the text the client receives, which is what the
    model sees.
    """

    def __init__(self, path: Path):
        self.path = path

    async def on_call_tool(self, context, call_next):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tool": context.message.name,
            "arguments": context.message.arguments or {},
        }
        try:
            result = await call_next(context)
        except Exception as error:  # e.g. ToolError: log it, then let FastMCP report it
            entry["error"] = str(error)
            self.write(entry)
            raise
        entry["response"] = [block.text for block in result.content if hasattr(block, "text")]
        self.write(entry)
        return result

    def write(self, entry: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as log:
            log.write(json.dumps(entry) + "\n")
