"""The plain-Python allergen logic, including the startup checks."""

from pathlib import Path

import pytest

from allergens import build_dish_allergens, normalise_allergen

DATA = Path(__file__).resolve().parent.parent / "data"
PUBLIC = (DATA / "public.md").read_text()
CONFIDENTIAL = (DATA / "confidential.md").read_text()


def test_allergens_match_the_menu():
    assert build_dish_allergens(PUBLIC, CONFIDENTIAL) == {
        "Super Awesome Salad": ["egg", "sesame", "dairy", "wheat"]
    }


@pytest.mark.parametrize(
    "word, expected",
    [
        ("milk", "milk"),
        ("Dairy", "milk"),
        ("wheat", "gluten"),
        ("  Tree   Nuts ", "tree nuts"),
        ("lemon", None),
        ("oil", None),
    ],
)
def test_normalise_allergen(word, expected):
    assert normalise_allergen(word) == expected


@pytest.mark.parametrize(
    "public, confidential, error",
    [
        (PUBLIC.replace("sesame, ", ""), CONFIDENTIAL, "don't match the public menu"),
        (PUBLIC, CONFIDENTIAL + "2 grams black pepper\n", "no allergen mapping"),
        (PUBLIC, CONFIDENTIAL + "a pinch of salt\n", "can't parse ingredient"),
        (PUBLIC.replace("Allergens:", "Contains:"), CONFIDENTIAL, "no 'Allergens:' line"),
    ],
    ids=["menu-mismatch", "unmapped-ingredient", "unparseable-line", "no-allergen-line"],
)
def test_startup_check_fails_loudly(public, confidential, error):
    with pytest.raises(ValueError, match=error):
        build_dish_allergens(public, confidential)
