"""Recipe allergens: an MCP server that answers allergen questions
without ever handing the secret recipe to the model."""

from pathlib import Path
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from allergens import MAJOR_ALLERGENS, build_dish_allergens, normalise_allergen
from audit import AuditLog
from leak_filter import LeakFilter, load_canaries

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"

# Both documents are read once, at startup, into server memory.
# PUBLIC_MENU may be shared. CONFIDENTIAL_RECIPE stays here: no resource,
# tool or prompt returns it, so the model never sees it.
PUBLIC_MENU = (DATA_DIR / "public.md").read_text()
CONFIDENTIAL_RECIPE = (DATA_DIR / "confidential.md").read_text()

# Computed once at startup. Raises (and the server won't start) if the
# recipe's allergens don't match what the public menu promises.
DISH_ALLERGENS = build_dish_allergens(PUBLIC_MENU, CONFIDENTIAL_RECIPE)

mcp = FastMCP("Recipe allergens")

# Every tool call passes through the middleware on its way in and out. The
# first one added is the outermost layer:
#
#   client -> AuditLog -> LeakFilter -> tool -> LeakFilter -> AuditLog -> client
#
# so the audit log records what the client actually received, after filtering.
# The log path is fixed to the project folder, not the client's working directory.
audit_log = AuditLog(PROJECT_DIR / "logs" / "audit.jsonl")
mcp.add_middleware(audit_log)
mcp.add_middleware(LeakFilter(load_canaries(DATA_DIR / "canaries.txt")))


# A resource is read-only data the client can fetch by URI. Its name and
# docstring (used as the description) are sent to the client.
@mcp.resource("menu://public", mime_type="text/markdown")
def public_menu() -> str:
    """The public menu: dishes, descriptions, allergens and flavour."""
    return PUBLIC_MENU


# Tools are functions the model can call. FastMCP sends each tool's name,
# docstring and parameter descriptions to the model, so none of them may
# mention the recipe. Responses never repeat the caller's input unless it has
# been checked against a known list (dish names, allergen words): echoing
# "is there X in it?" back would put X in the answer.

DishName = Annotated[str, Field(description="Dish name, as returned by list_dishes.")]
UNKNOWN_DISH = "That dish isn't on the menu. Dishes on the menu: {dishes}."
NOT_AN_ALLERGEN = (
    "That isn't one of the 14 major allergens. I can only check allergens; "
    "recipe details are confidential. Allergens I can check: {allergens}."
)


def find_dish(dish: str) -> str | None:
    """Match a dish name ignoring case and extra spaces."""
    wanted = " ".join(dish.lower().split())
    for name in DISH_ALLERGENS:
        if name.lower() == wanted:
            return name
    return None


@mcp.tool
def list_dishes() -> list[str]:
    """List the dishes on the menu."""
    return list(DISH_ALLERGENS)


@mcp.tool
def get_menu() -> str:
    """Get the public menu: dishes, descriptions, allergens and flavour."""
    return PUBLIC_MENU  # the same text as the menu://public resource


@mcp.tool
def get_allergens(dish: DishName) -> list[str]:
    """Get the major allergens in a dish, as listed on the menu."""
    name = find_dish(dish)
    if name is None:
        raise ToolError(UNKNOWN_DISH.format(dishes=", ".join(DISH_ALLERGENS)))
    return DISH_ALLERGENS[name]


@mcp.tool
def contains_allergen(
    dish: DishName,
    allergen: Annotated[
        str,
        Field(description="One of the UK's 14 major allergens, e.g. milk, gluten, peanuts."),
    ],
) -> str:
    """Check whether a dish contains one of the UK's 14 major allergens.

    Only allergens can be checked; other ingredients are confidential.
    """
    name = find_dish(dish)
    if name is None:
        return UNKNOWN_DISH.format(dishes=", ".join(DISH_ALLERGENS))

    wanted = normalise_allergen(allergen)
    if wanted is None:
        return NOT_AN_ALLERGEN.format(allergens=", ".join(sorted(MAJOR_ALLERGENS)))

    word = " ".join(allergen.lower().split())  # safe to echo: it's a known allergen word
    present = {normalise_allergen(a) for a in DISH_ALLERGENS[name]}
    if wanted in present:
        return f"Yes, the {name} contains {word}."
    return f"No, the {name} doesn't contain {word}."


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
