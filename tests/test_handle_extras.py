import pytest
from decimal import Decimal
from mscrInventory.importers.handle_extras import handle_extras
from mscrInventory.models import Ingredient, RecipeModifier, ModifierBehavior


@pytest.mark.django_db
def test_extra_bacon_scales_correctly():
    bacon = Ingredient.objects.create(name="Bacon", type="TOPPING")
    RecipeModifier.objects.create(
        name="Extra Bacon",
        type="TOPPING",
        behavior=ModifierBehavior.SCALE,
        ingredient=bacon,
        base_quantity=1,
        unit="slice",
        quantity_factor=Decimal("2.0"),
        target_selector={"by_name": ["Bacon"]},
    )

    recipe_map = {"Bacon": {"qty": Decimal("1.0"), "type": "TOPPING"}}
    result = handle_extras("Extra Bacon", recipe_map)

    assert "Bacon" in result
    assert result["Bacon"]["qty"] == Decimal("2.0")


@pytest.mark.django_db
def test_lite_sugar_scales_down():
    sugar = Ingredient.objects.create(name="Sugar", type="SUGAR")
    RecipeModifier.objects.create(
        name="Lite Sugar",
        type="SUGAR",
        behavior=ModifierBehavior.SCALE,
        ingredient=sugar,
        base_quantity=1,
        unit="g",
        quantity_factor=Decimal("0.4"),
        target_selector={"by_type": ["SUGAR"]},
    )

    recipe_map = {"Sugar": {"qty": Decimal("10.0"), "type": "SUGAR"}}
    result = handle_extras("Lite Sugar", recipe_map)

    assert result["Sugar"]["qty"] == Decimal("4.0")


@pytest.mark.django_db
def test_oat_milk_replaces_milk():
    milk = Ingredient.objects.create(name="Whole Milk", type="MILK")
    oat = Ingredient.objects.create(name="Oat Milk", type="MILK")
    RecipeModifier.objects.create(
        name="Oat Milk",
        type="MILK",
        behavior=ModifierBehavior.REPLACE,
        ingredient=oat,
        base_quantity=1,
        unit="oz",
        target_selector={"by_type": ["MILK"]},
        replaces={"to": [["Oat Milk", 1.0]]},
    )

    recipe_map = {"Whole Milk": {"qty": Decimal("8.0"), "type": "MILK"}}
    result = handle_extras("Oat Milk", recipe_map)

    assert "Oat Milk" in result
    assert "Whole Milk" not in result
    assert result["Oat Milk"]["qty"] == Decimal("8.0")


@pytest.mark.django_db
def test_split_coldbrew_handles_two_way_blend():
    base = Ingredient.objects.create(name="Cold Brew Base", type="COFFEE")
    RecipeModifier.objects.create(
        name="Split Cold Brew",
        type="COFFEE",
        behavior=ModifierBehavior.REPLACE,
        ingredient=base,
        base_quantity=1,
        unit="oz",
        target_selector={"by_type": ["COFFEE"]},
        replaces={"to": [["Dark Cold Brew", 0.5], ["White Cold Brew", 0.5]]},
    )

    recipe_map = {"Cold Brew Base": {"qty": Decimal("6.0"), "type": "COFFEE"}}
    result = handle_extras("Split Cold Brew", recipe_map)

    total = sum(v["qty"] for v in result.values())
    assert round(total, 2) == Decimal("6.0")
    assert all("Cold Brew" in name for name in result.keys())


@pytest.mark.django_db
def test_split_coldbrew_handles_three_way_blend():
    base = Ingredient.objects.create(name="Cold Brew Base", type="COFFEE")
    RecipeModifier.objects.create(
        name="Split Cold Brew 3-Way",
        type="COFFEE",
        behavior=ModifierBehavior.REPLACE,
        ingredient=base,
        base_quantity=1,
        unit="oz",
        target_selector={"by_type": ["COFFEE"]},
        replaces={"to": [
            ["Dark Cold Brew", 0.33],
            ["Medium Cold Brew", 0.33],
            ["White Cold Brew", 0.34],
        ]},
    )

    recipe_map = {"Cold Brew Base": {"qty": Decimal("9.0"), "type": "COFFEE"}}
    result = handle_extras("Split Cold Brew 3-Way", recipe_map)

    total = sum(v["qty"] for v in result.values())
    assert round(total, 2) == Decimal("9.0")
    assert len(result) == 3


@pytest.mark.django_db
def test_dirty_chai_replaces_and_adds():
    milk = Ingredient.objects.create(name="Whole Milk", type="MILK")
    chai = Ingredient.objects.create(name="Chai Milk Blend", type="MILK")
    espresso = Ingredient.objects.create(name="Espresso Shot", type="EXTRA")

    modifier = RecipeModifier.objects.create(
        name="Dirty Chai",
        type="MILK",
        behavior=ModifierBehavior.REPLACE,
        ingredient=chai,
        base_quantity=1,
        unit="oz",
        target_selector={"by_type": ["MILK"]},
        replaces={"to": [["Chai Milk Blend", 1.0]]},
    )
    modifier.expands_to.add(espresso)

    recipe_map = {"Whole Milk": {"qty": Decimal("8.0"), "type": "MILK"}}
    result = handle_extras("Dirty Chai", recipe_map)

    assert "Chai Milk Blend" in result
    assert "Espresso Shot" in result
    assert "Whole Milk" not in result
