# secret-recipe-mcp

A small [MCP](https://modelcontextprotocol.io) server, built with
[FastMCP](https://gofastmcp.com), that answers allergen questions about a dish
whose sauce recipe is secret. The recipe never reaches the model.

## Why

In [cheating-evals](https://github.com/franciscaconcha/cheating-evals)
([blog post](https://francisca.cr/writing/my-inspect-project/)), a food-delivery
chatbot had a confidential recipe in its system prompt and was told to share
only allergen information. Models never leaked the recipe outright, but details
slipped out in honest refusals ("I can't say what *oil* it uses"), and some
replies lied ("I don't have that information"). 

This project tries the opposite design. It implements an MCP server with tools to find the allergen information. The model does not have access to the confidential recipes at all. This works as an extension of [cheating-evals](https://github.com/franciscaconcha/cheating-evals) both to compare the different behaviours and to teach myself how to build my own MCP server.

## Design: guardrails in code, not in the prompt

The server loads the recipe at startup and keeps it in memory. No tool,
resource or description ever returns it. Instead of trusting the model to
withhold a secret it can see, the model is never given the secret, so
"I don't have access to the recipe" becomes true. Allergens are computed from
the recipe in plain Python and checked against the public menu: the server
refuses to start if they disagree, or if an ingredient has no allergen mapping.
`contains_allergen` only answers for the UK's 14 major allergens. For anything
else it gives the same refusal, so it never confirms or denies an ingredient.
As a backstop, a middleware blocks any response that contains a secret word,
and another logs every tool call to `logs/audit.jsonl`.

## What the model can use

| | |
| --- | --- |
| `menu://public` (resource) | The public menu |
| `list_dishes()` | Dish names |
| `get_menu()` | The public menu, as a tool (some clients only offer tools to the model) |
| `get_allergens(dish)` | Allergens, in the menu's words |
| `contains_allergen(dish, allergen)` | Yes/no for a major allergen; an honest refusal for anything else |

## Run it

Requires [uv](https://docs.astral.sh/uv/), and Node.js for the Inspector.

```sh
uv run pytest                                   # tests, including leak tests
uv run fastmcp dev inspector src/server.py      # try the tools by hand
uv run --env-file .env src/agent.py             # chat with the Pydantic AI agent
./chat/run.sh                                   # chat with Claude Code, menu in the prompt
./chat/run.sh --no-menu                         # chat without the menu: tools only
```

The agent and the live tests need an Anthropic API key. Put it in a `.env`
file (`ANTHROPIC_API_KEY=...`), which git ignores. Without it, the live tests
are skipped.

```sh
uv run --env-file .env pytest -m live -rw       # live tests only, with flagged replies
```

`chat/run.sh` starts Claude Code with the eval's system prompt (without the
confidential document), no built-in tools (so it can't read the recipe from
disk), and only this server.

## The chat agent

`src/agent.py` is a small command-line agent built with
[Pydantic AI](https://ai.pydantic.dev). Its only tools are this server's, and
its prompt doesn't mention any recipe. It starts the server as a subprocess,
keeps the conversation history between turns, and prints each tool call to the
console (`[tool] ...`). Use `--model` to pick another model (default: Claude Opus 5.5).

Its tests in `tests/test_agent.py` come in two kinds:

- **Offline:** a scripted model stands in for Claude, so they're free and give
  the same result every run. They test the wiring, the history, and that the
  server's refusal reaches the model unchanged.
- **Live** (marked `live`): Claude answers normal questions, non-allergen
  questions, subtle extraction attempts, prompt injection and emotional
  pressure. A canary word in anything the server sent fails the test. A
  canary word in Claude's reply only raises a `PossibleLeakWarning` for a
  person to read, because Claude can guess ingredients from the public
  allergens without ever seeing the recipe.

## What happened

Across 14 questions per version, there were no leaks and no dishonest answers
(see [NOTES.md](NOTES.md)). One limitation remains, and no server can fix it:
the public allergen list itself narrows down the recipe. Asked for a home-made
substitute, the model suggested mayonnaise and sesame oil, two of the real
ingredients, by working backwards from "egg, sesame".

## Layout

```
src/server.py       MCP server: resource, tools, middleware setup
src/agent.py        Pydantic AI chat agent that uses the server
src/allergens.py    recipe parsing and allergen logic (no MCP)
src/audit.py        audit log middleware
src/leak_filter.py  leak filter middleware
tests/              pytest suite
chat/               Claude Code launcher and system prompts
data/               public menu, confidential recipe, canary words
```
