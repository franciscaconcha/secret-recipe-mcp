"""Normal behaviour of the resource, the tools and the audit log."""

import json

import pytest

import server
from conftest import text_of

SALAD = "Super Awesome Salad"


async def test_public_menu_resource(client):
    [contents] = await client.read_resource("menu://public")
    assert contents.text == server.PUBLIC_MENU


async def test_list_dishes(client):
    result = await client.call_tool("list_dishes", {})
    assert result.data == [SALAD]


async def test_get_allergens_uses_menu_words(client):
    result = await client.call_tool("get_allergens", {"dish": SALAD})
    assert result.data == ["egg", "sesame", "dairy", "wheat"]


async def test_get_allergens_ignores_case_and_spaces(client):
    result = await client.call_tool("get_allergens", {"dish": "  super   AWESOME salad "})
    assert result.data == ["egg", "sesame", "dairy", "wheat"]


async def test_get_allergens_unknown_dish_is_an_error(client):
    result = await client.call_tool("get_allergens", {"dish": "Pizza"}, raise_on_error=False)
    assert result.is_error
    assert "isn't on the menu" in text_of(result)


@pytest.mark.parametrize("allergen", ["egg", "sesame", "dairy", "milk", "wheat", "gluten"])
async def test_contains_allergen_yes(client, allergen):
    result = await client.call_tool("contains_allergen", {"dish": SALAD, "allergen": allergen})
    assert text_of(result) == f"Yes, the {SALAD} contains {allergen}."


@pytest.mark.parametrize("allergen", ["peanuts", "mustard", "fish", "soy", "celery"])
async def test_contains_allergen_no(client, allergen):
    result = await client.call_tool("contains_allergen", {"dish": SALAD, "allergen": allergen})
    assert text_of(result) == f"No, the {SALAD} doesn't contain {allergen}."


@pytest.mark.parametrize("word", ["lemon", "olive oil", "basil", "chicken"])
async def test_contains_allergen_refuses_non_allergens(client, word):
    result = await client.call_tool("contains_allergen", {"dish": SALAD, "allergen": word})
    answer = text_of(result)
    assert answer.startswith("That isn't one of the 14 major allergens.")
    assert "confidential" in answer
    assert word not in answer  # doesn't repeat the question back


async def test_contains_allergen_unknown_dish(client):
    result = await client.call_tool("contains_allergen", {"dish": "Pizza", "allergen": "egg"})
    assert "isn't on the menu" in text_of(result)


async def test_audit_log_records_each_call(client):
    await client.call_tool("contains_allergen", {"dish": SALAD, "allergen": "egg"})
    await client.call_tool("get_allergens", {"dish": "Pizza"}, raise_on_error=False)

    first, second = [json.loads(line) for line in server.audit_log.path.read_text().splitlines()]
    assert first["tool"] == "contains_allergen"
    assert first["arguments"] == {"dish": SALAD, "allergen": "egg"}
    assert first["response"] == [f"Yes, the {SALAD} contains egg."]
    assert "timestamp" in first
    assert second["tool"] == "get_allergens"
    assert "isn't on the menu" in second["error"]
