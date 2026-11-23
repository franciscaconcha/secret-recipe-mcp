# guarded-recipe-mcp

A small [MCP](https://modelcontextprotocol.io) server, built with
[FastMCP](https://gofastmcp.com), that answers allergen questions about a dish
whose sauce recipe is secret. The recipe never reaches the model.

## Why

In [cheating-evals](https://github.com/franciscaconcha/cheating-evals)
([blog post](https://francisca.cr/writing/my-inspect-project/)), a food-delivery
chatbot had a confidential recipe in its system prompt and was told to share
only allergen information. Models never leaked the recipe outright, but details
slipped out in honest refusals ("I can't say what *oil* it uses"), and some
replies lied ("I don't have that information"). This project tries the
opposite design.

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
| `get_allergens(dish)` | Allergens, in the menu's words |
| `contains_allergen(dish, allergen)` | Yes/no for a major allergen; an honest refusal for anything else |

## Run it

Requires [uv](https://docs.astral.sh/uv/), and Node.js for the Inspector.

```sh
uv run pytest                                   # tests, including leak tests
uv run fastmcp dev inspector src/server.py      # try the tools by hand
./chat/run.sh                                   # chat with Claude Code, menu in the prompt
./chat/run.sh --no-menu                         # chat without the menu: tools only
```

`chat/run.sh` starts Claude Code with the eval's system prompt (without the
confidential document), no built-in tools (so it can't read the recipe from
disk), and only this server.

## What happened

Across 14 questions per version, there were no leaks and no dishonest answers
(see [NOTES.md](NOTES.md)). One limitation remains, and no server can fix it:
the public allergen list itself narrows down the recipe. Asked for a home-made
substitute, the model suggested mayonnaise and sesame oil, two of the real
ingredients, by working backwards from "egg, sesame".

## Layout

```
src/server.py       MCP server: resource, tools, middleware setup
src/allergens.py    recipe parsing and allergen logic (no MCP)
src/audit.py        audit log middleware
src/leak_filter.py  leak filter middleware
tests/              pytest suite
chat/               Claude Code launcher and system prompts
data/               public menu, confidential recipe, canary words
```
