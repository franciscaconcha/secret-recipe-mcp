"""The Pydantic AI agent, wired to the MCP server.

Offline tests: a scripted FunctionModel stands in for Claude, so they need no
API key and give the same result every run. The server is connected in memory
(see the `client` fixture in conftest.py for why the audit log is redirected).
"""

import pytest
from pydantic_ai.messages import (
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import FunctionModel

import agent
import server
from allergens import MAJOR_ALLERGENS
from leak_filter import find_leaks, load_canaries

SALAD = "Super Awesome Salad"
CANARIES = load_canaries(server.DATA_DIR / "canaries.txt")


@pytest.fixture(autouse=True)
def temporary_audit_log(tmp_path, monkeypatch):
    monkeypatch.setattr(server.audit_log, "path", tmp_path / "audit.jsonl")


def tool_results(messages) -> list[str]:
    """Everything the server sent back to the model: tool results, and tool
    errors (which Pydantic AI hands to the model as retry prompts)."""
    results = []
    for message in messages:
        for part in message.parts:
            if isinstance(part, ToolReturnPart):
                results.append(str(part.content))
            elif isinstance(part, RetryPromptPart) and part.tool_name:
                results.append(str(part.content))
    return results


def scripted(tool_name: str, args: dict):
    """A fake model: call one tool, then reply with exactly what the tool said."""

    def model(messages, info):
        last = messages[-1].parts[-1]
        if isinstance(last, (ToolReturnPart, RetryPromptPart)):
            return ModelResponse(parts=[TextPart(str(last.content))])
        return ModelResponse(parts=[ToolCallPart(tool_name, args)])

    return FunctionModel(model)


def make_agent(model):
    return agent.build_agent(model, agent.make_server(server.mcp))


async def test_tool_call_is_answered_and_logged(capsys):
    bot = make_agent(scripted("contains_allergen", {"dish": SALAD, "allergen": "egg"}))
    async with bot:
        result = await bot.run("Is there egg in the salad?")

    assert result.output == f"Yes, the {SALAD} contains egg."
    logged = capsys.readouterr().err
    assert f'[tool] contains_allergen({{"dish": "{SALAD}", "allergen": "egg"}})' in logged
    assert f"[tool] -> Yes, the {SALAD} contains egg." in logged


async def test_honest_refusal_reaches_the_model_unchanged():
    """The key guardrail, end to end: a non-allergen question gets the server's
    fixed refusal, which neither repeats the guess nor reveals the recipe."""
    bot = make_agent(scripted("contains_allergen", {"dish": SALAD, "allergen": "lemon"}))
    async with bot:
        result = await bot.run("Is there lemon in the house sauce?")

    refusal = server.NOT_AN_ALLERGEN.format(allergens=", ".join(sorted(MAJOR_ALLERGENS)))
    [returned] = tool_results(result.all_messages())
    assert returned == refusal
    assert "lemon" not in returned
    assert find_leaks(returned, CANARIES) == []


async def test_tool_error_reaches_the_model_and_is_logged(capsys):
    bot = make_agent(scripted("get_allergens", {"dish": "Pizza"}))
    async with bot:
        result = await bot.run("What allergens are in the pizza?")

    [returned] = tool_results(result.all_messages())
    assert "isn't on the menu" in returned
    assert "[tool] !! That dish isn't on the menu" in capsys.readouterr().err


async def test_history_is_kept_between_turns():
    seen_in_second_turn = []

    def model(messages, info):
        if any(isinstance(p, UserPromptPart) and p.content == "And peanuts?"
               for p in messages[-1].parts):
            seen_in_second_turn.extend(
                p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart)
            )
        return ModelResponse(parts=[TextPart("ok")])

    bot = make_agent(FunctionModel(model))
    async with bot:
        first = await bot.run("Is there egg in the salad?")
        await bot.run("And peanuts?", message_history=first.all_messages())

    assert seen_in_second_turn == ["Is there egg in the salad?", "And peanuts?"]


async def test_only_the_mcp_tools_are_offered():
    offered = []

    def model(messages, info):
        offered.extend(tool.name for tool in info.function_tools)
        return ModelResponse(parts=[TextPart("ok")])

    bot = make_agent(FunctionModel(model))
    async with bot:
        await bot.run("hi")

    assert sorted(offered) == ["contains_allergen", "get_allergens", "list_dishes"]
