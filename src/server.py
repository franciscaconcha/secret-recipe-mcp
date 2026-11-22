"""Recipe allergens: an MCP server that answers allergen questions
without ever handing the secret recipe to the model."""

from pathlib import Path

from fastmcp import FastMCP

from allergens import build_dish_allergens

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Both documents are read once, at startup, into server memory.
# PUBLIC_MENU may be shared. CONFIDENTIAL_RECIPE stays here: no resource,
# tool or prompt returns it, so the model never sees it.
PUBLIC_MENU = (DATA_DIR / "public.md").read_text()
CONFIDENTIAL_RECIPE = (DATA_DIR / "confidential.md").read_text()

# Computed once at startup. Raises (and the server won't start) if the
# recipe's allergens don't match what the public menu promises.
DISH_ALLERGENS = build_dish_allergens(PUBLIC_MENU, CONFIDENTIAL_RECIPE)

mcp = FastMCP("Recipe allergens")


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
