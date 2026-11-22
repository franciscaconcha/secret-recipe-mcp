"""Shared test fixtures.

Tests talk to the server through a real MCP client, connected in memory:
same protocol messages as stdio, without starting a subprocess.
"""

import pytest
from fastmcp import Client

import server


@pytest.fixture
async def client(tmp_path, monkeypatch):
    # Send the audit log to a temporary file so tests don't fill the real one.
    monkeypatch.setattr(server.audit_log, "path", tmp_path / "audit.jsonl")
    async with Client(server.mcp) as client:
        yield client


def text_of(result) -> str:
    """All the text a client would show the model for a tool result."""
    return "\n".join(block.text for block in result.content if hasattr(block, "text"))
