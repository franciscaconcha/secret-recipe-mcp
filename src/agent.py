"""A command-line chat agent for allergen questions, built with Pydantic AI.

The agent's only source of information is the recipe MCP server. It has no
file access, and the recipe isn't in its prompt, so it can't see the recipe.

    uv run src/agent.py                      # default model
    uv run src/agent.py --model anthropic:claude-sonnet-5-5
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import pydantic_ai
from fastmcp.client.transports import PythonStdioTransport
from pydantic_ai import Agent
from pydantic_ai.exceptions import AgentRunError
from pydantic_ai.mcp import MCPToolset

PROJECT_DIR = Path(__file__).resolve().parent.parent
SERVER_SCRIPT = PROJECT_DIR / "src" / "server.py"
SERVER_LOG = PROJECT_DIR / "logs" / "server.log"  # the server's stderr (banner, logs)
DEFAULT_MODEL = "anthropic:claude-opus-5-5"

SYSTEM_PROMPT = """\
You are an assistant for a food delivery app. You only answer allergen
questions about dishes on the menu. You don't know the menu yourself: use your
tools for every answer, and don't guess. If a question isn't about allergens,
politely say you can only help with allergen questions."""


def as_text(result):
    """Turn a list of words into one string: ["egg", "sesame"] -> "egg, sesame".

    Pydantic AI sends each item of a list result to Claude as a separate text
    block, and Claude reads the blocks run together ("eggsesame").
    """
    if isinstance(result, list) and all(isinstance(item, str) for item in result):
        return ", ".join(result)
    return result


async def log_tool_call(ctx, call_tool, name, args):
    """Print each tool call and its result to stderr, then pass the result on.

    Pydantic AI calls this instead of calling the tool directly; `call_tool`
    is the real call. Errors are logged and re-raised, so the agent still
    handles them as usual. List results are joined into one string first
    (see `as_text`).
    """
    print(f"[tool] {name}({json.dumps(args)})", file=sys.stderr)
    try:
        result = as_text(await call_tool(name, args))
    except Exception as error:
        print(f"[tool] !! {error}", file=sys.stderr)
        raise
    print(f"[tool] -> {result}", file=sys.stderr)
    return result


def make_server(connect_to=None) -> MCPToolset:
    """The recipe MCP server, started as a subprocess with this venv's Python.

    Its stderr goes to logs/server.log, so it doesn't mix with the chat.
    Tests pass the FastMCP server object as `connect_to` to connect in memory
    instead, like `Client(server.mcp)` in tests/conftest.py.
    """
    if connect_to is None:
        SERVER_LOG.parent.mkdir(exist_ok=True)
        connect_to = PythonStdioTransport(
            SERVER_SCRIPT, cwd=str(PROJECT_DIR), python_cmd=sys.executable, log_file=SERVER_LOG
        )
    return MCPToolset(connect_to, process_tool_call=log_tool_call)


def build_agent(model, server: MCPToolset) -> Agent:
    """An agent whose only tools are the MCP server's."""
    return Agent(model, system_prompt=SYSTEM_PROMPT, toolsets=[server])


async def chat(agent: Agent) -> None:
    """Read questions, answer them, and keep the conversation history between turns."""
    history = []
    async with agent:  # starts the MCP server and connects; stops it on exit
        print("Ask about allergens on the menu. Type 'quit' to leave.")
        while True:
            try:
                question = await asyncio.to_thread(input, "> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if question.strip().lower() in {"quit", "exit"}:
                break
            if not question.strip():
                continue
            try:
                result = await agent.run(question, message_history=history)
            except AgentRunError as error:  # e.g. too many failed tool calls in one turn
                print(f"Sorry, something went wrong with that question ({error}). Please try again.")
                continue  # history is unchanged, so the failed turn is forgotten
            history = result.all_messages()  # everything so far, sent along next turn
            print(result.output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"default: {DEFAULT_MODEL}")
    args = parser.parse_args()
    pydantic_ai.BANNER_ENABLED = False  # keep the console for the chat and [tool] lines
    try:
        asyncio.run(chat(build_agent(args.model, make_server())))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
