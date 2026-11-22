"""Allergen logic in plain Python. Nothing in this module knows about MCP.

Error messages here point to line numbers rather than quoting the recipe,
so even a startup failure doesn't print a secret ingredient.
"""

import re

# The UK's 14 major allergens (Food Information Regulations 2014), short names.
MAJOR_ALLERGENS = {
    "celery",
    "gluten",  # cereals containing gluten
    "crustaceans",
    "egg",
    "fish",
    "lupin",
    "milk",
    "molluscs",
    "mustard",
    "peanuts",
    "sesame",
    "soya",
    "sulphites",
    "tree nuts",
}

# Everyday words people use for the same allergens.
SYNONYMS = {
    "dairy": "milk",
    "wheat": "gluten",
    "cereals containing gluten": "gluten",
    "eggs": "egg",
    "crustacean": "crustaceans",
    "shellfish": "crustaceans",
    "mollusc": "molluscs",
    "peanut": "peanuts",
    "nuts": "tree nuts",
    "tree nut": "tree nuts",
    "soy": "soya",
    "sulphur dioxide": "sulphites",
    "sulfites": "sulphites",
}

# Hand-written: which allergens each ingredient brings. Every ingredient a dish
# uses must appear here, even with no allergens, so a new ingredient can't
# slip through unchecked.
INGREDIENT_ALLERGENS = {
    # Public components
    "iceberg lettuce": set(),
    "grilled chicken": set(),
    "parmesan": {"milk"},
    "croutons": {"gluten"},
    # House sauce (confidential)
    "smoked dried oregano": set(),
    "belgian mayonnaise": {"egg"},
    "sesame oil": {"sesame"},
    "earl grey tea": set(),
}

# What each dish is made of, as stated on the public menu. "house sauce" is
# expanded from the confidential recipe at startup.
DISH_COMPONENTS = {
    "Super Awesome Salad": [
        "iceberg lettuce",
        "grilled chicken",
        "parmesan",
        "croutons",
        "house sauce",
    ],
}

RECIPE_LINE = re.compile(
    r"^[\d.]+\s+(?:grams?|teaspoons?|tablespoons?)\s+(?P<name>.+)$", re.IGNORECASE
)


def normalise_allergen(word: str) -> str | None:
    """Map a word to one of the 14 major allergens, or None if it isn't one."""
    word = " ".join(word.lower().split())
    word = SYNONYMS.get(word, word)
    return word if word in MAJOR_ALLERGENS else None


def parse_recipe(text: str) -> list[str]:
    """Turn the confidential recipe into a list of ingredient names."""
    ingredients = []
    for number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line or line.endswith(":"):  # blank line or heading
            continue
        match = RECIPE_LINE.match(line)
        if not match:
            raise ValueError(f"confidential.md line {number}: can't parse ingredient")
        ingredients.append(match["name"].lower())
    if not ingredients:
        raise ValueError("confidential.md: no ingredients found")
    return ingredients


def parse_public_allergens(text: str) -> dict[str, str]:
    """Read the 'Allergens: ...' line from the public menu.

    Returns {standard name: word used on the menu}, in menu order,
    e.g. {"milk": "dairy"}.
    """
    match = re.search(r"^Allergens:(.*)$", text, re.IGNORECASE | re.MULTILINE)
    if not match:
        raise ValueError("public.md: no 'Allergens:' line")
    allergens = {}
    for word in match[1].split(","):
        allergen = normalise_allergen(word)
        if allergen is None:
            raise ValueError(f"public.md: {word.strip()!r} isn't a major allergen")
        allergens[allergen] = word.strip()
    return allergens


def compute_allergens(ingredients: list[str]) -> set[str]:
    """Union of the allergens of every ingredient."""
    allergens = set()
    for position, ingredient in enumerate(ingredients, start=1):
        if ingredient not in INGREDIENT_ALLERGENS:
            raise ValueError(f"ingredient #{position} has no allergen mapping")
        allergens |= INGREDIENT_ALLERGENS[ingredient]
    return allergens


def build_dish_allergens(public_md: str, confidential_md: str) -> dict[str, list[str]]:
    """Compute each dish's allergens and check them against the public menu.

    Returns {dish: allergens}, in the menu's words and order.
    Raises ValueError if anything doesn't line up, so the server refuses
    to start rather than give a wrong allergen answer.
    """
    for ingredient, allergens in INGREDIENT_ALLERGENS.items():
        unknown = allergens - MAJOR_ALLERGENS
        if unknown:
            raise ValueError(f"mapping for {ingredient!r} uses unknown allergens {unknown}")

    sauce = parse_recipe(confidential_md)
    published = parse_public_allergens(public_md)

    result = {}
    for dish, components in DISH_COMPONENTS.items():
        if dish.lower() not in public_md.lower():
            raise ValueError(f"public.md doesn't mention dish {dish!r}")
        ingredients = []
        for component in components:
            ingredients += sauce if component == "house sauce" else [component]
        computed = compute_allergens(ingredients)
        if computed != set(published):
            raise ValueError(
                f"{dish}: computed allergens {sorted(computed)} "
                f"don't match the public menu {sorted(published)}"
            )
        # They match, so answer in the words customers see on the menu.
        result[dish] = list(published.values())
    return result
