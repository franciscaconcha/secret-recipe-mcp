"""Leak filter: a second guardrail that checks every tool response for
secret words before it leaves the server.

The tools are written not to leak; this catches it if one ever does.
"""

import json
import re
from pathlib import Path

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware

WITHHELD = "Response withheld: it would have revealed confidential recipe details."


def load_canaries(path: Path) -> list[str]:
    """Read canaries.txt: one fact per line, variants separated by '|'."""
    canaries = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            canaries += [variant.strip() for variant in line.split("|") if variant.strip()]
    return canaries


def find_leaks(text: str, canaries: list[str]) -> list[str]:
    """Canaries that appear in text as whole words, ignoring case."""
    return [
        canary
        for canary in canaries
        if re.search(rf"\b{re.escape(canary)}\b", text, re.IGNORECASE)
    ]


class LeakFilter(Middleware):
    """Block any tool response that contains a canary.

    Unlike AuditLog, this middleware changes what the client gets: if a
    response contains a secret word, the client receives an error instead.
    """

    def __init__(self, canaries: list[str]):
        self.canaries = canaries

    async def on_call_tool(self, context, call_next):
        result = await call_next(context)
        # Check everything the client could show the model: the text blocks
        # and the structured copy of the result.
        texts = [block.text for block in result.content if hasattr(block, "text")]
        everything = "\n".join(texts) + "\n" + json.dumps(result.structured_content)
        if find_leaks(everything, self.canaries):
            raise ToolError(WITHHELD)  # don't say which word: that would leak it
        return result
