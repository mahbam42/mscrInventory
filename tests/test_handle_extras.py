from decimal import Decimal

import pytest

from mscrInventory.models import (
    Category,
    Ingredient,
    IngredientType,
    Product,
    RecipeItem,
    RecipeModifier,
    ModifierBehavior,
)
from importers._handle_extras import handle_extras


def _recipe_entry(qty: Decimal | float | str, ingredient_type: IngredientType | None):
    quantity = qty if isinstance(qty, Decimal) else Decimal(str(qty))
    type_name = getattr(ingredient_type, "name", "") or ""
    type_id = getattr(ingredient_type, "id", None)
    return {
        "qty": quantity,
        "type_id": type_id,
        "type_name": type_name,
        "type": type_name,
    }


@pytest.fixture
def ingredient_types(db):
    names = ["Milk", "Topping", "Sugar", "Flavor", "Extra", "Coffee"]
    types = {}
    for name in names:
        obj, _ = IngredientType.objects.get_or_create(name=name)
        types[name.upper()] = obj
    return types


@pytest.mark.django_db
def test_extra_bacon_scales_correctly(ingredient_types):
    bacon_type = ingredient_types["TOPPING"]
    bacon = Ingredient.objects.create(name="Bacon", type=bacon_type)
    RecipeModifier.objects.create(
        name="Extra Bacon",
        ingredient_type=bacon_type,
        behavior=ModifierBehavior.SCALE,
        ingredient=bacon,
        base_quantity=1,
        unit="slice",
        quantity_factor=Decimal("2.0"),
        target_selector={"by_name": ["Bacon"]},
    )

    recipe_map = {"Bacon": _recipe_entry("1.0", bacon_type)}
    result, log = handle_extras("Extra Bacon", recipe_map, [])

    assert "Bacon" in result
    assert result["Bacon"]["qty"] == Decimal("2.00")
    assert log["behavior"] == ModifierBehavior.SCALE
    assert log["replaced"] == []
    assert log["added"] == []


@pytest.mark.django_db
def test_lite_sugar_scales_down(ingredient_types):
    sugar_type = ingredient_types["SUGAR"]
    sugar = Ingredient.objects.create(name="Sugar", type=sugar_type)
    RecipeModifier.objects.create(
        name="Lite Sugar",
        ingredient_type=sugar_type,
        behavior=ModifierBehavior.SCALE,
        ingredient=sugar,
        base_quantity=1,
        unit="g",
        quantity_factor=Decimal("0.4"),
        target_selector={"by_type": [sugar_type.id]},
    )

    recipe_map = {"Sugar": _recipe_entry("10.0", sugar_type)}
    result, log = handle_extras("Lite Sugar", recipe_map, [])

    assert "Sugar" in result
    assert result["Sugar"]["qty"] == Decimal("4.00")
    assert log["behavior"] == ModifierBehavior.SCALE


@pytest.mark.django_db
def test_oat_milk_replaces_milk(ingredient_types):
    milk_type = ingredient_types["MILK"]
    milk = Ingredient.objects.create(name="Whole Milk", type=milk_type)
    oat = Ingredient.objects.create(name="Oat Milk", type=milk_type)
    RecipeModifier.objects.create(
        name="Oat Milk",
        ingredient_type=milk_type,
        behavior=ModifierBehavior.REPLACE,
        ingredient=oat,
        base_quantity=1,
        unit="oz",
        target_selector={"by_type": [milk_type.id]},
        replaces={"to": [["Oat Milk", 1.0]]},
    )

    recipe_map = {"Whole Milk": _recipe_entry("8.0", milk_type)}
    result, log = handle_extras("Oat Milk", recipe_map, [])

    assert "Oat Milk" in result
    assert log["behavior"] == ModifierBehavior.REPLACE
    assert ("Whole Milk", "Oat Milk") in log["replaced"]


@pytest.mark.django_db
def test_split_coldbrew_handles_two_way_blend(ingredient_types):
    coffee_type = ingredient_types["COFFEE"]
    base = Ingredient.objects.create(name="Cold Brew Base", type=coffee_type)
    RecipeModifier.objects.create(
        name="Split Cold Brew",
        ingredient_type=coffee_type,
        behavior=ModifierBehavior.REPLACE,
        ingredient=base,
        base_quantity=1,
        unit="oz",
        target_selector={"by_type": [coffee_type.id]},
        replaces={"to": [["Dark Cold Brew", 0.5], ["Medium Cold Brew", 0.5]]},
    )

    recipe_map = {"Cold Brew Base": _recipe_entry("6.0", coffee_type)}
    result, log = handle_extras("Split Cold Brew", recipe_map, [])

    assert log["behavior"] == ModifierBehavior.REPLACE
    assert any("Cold Brew" in key for key in result.keys())


@pytest.mark.django_db
def test_size_modifier_not_ignored_when_rule_exists(ingredient_types):
    coffee_type = ingredient_types["COFFEE"]
    dark = Ingredient.objects.create(name="Dark Coldbrew", type=coffee_type)
    medium = Ingredient.objects.create(name="Medium Coldbrew", type=coffee_type)
    RecipeModifier.objects.create(
        name="medium",
        ingredient_type=coffee_type,
        behavior=ModifierBehavior.REPLACE,
        ingredient=medium,
        base_quantity=Decimal("22.0"),
        unit="fl_oz",
        target_selector={"by_name": ["Dark Coldbrew"]},
    )

    recipe_map = {"Dark Coldbrew": _recipe_entry("16.0", coffee_type)}
    result, log = handle_extras("medium", recipe_map, [], recipe_context=list(recipe_map.keys()))

    assert "Medium Coldbrew" in result
    assert log["behavior"] == ModifierBehavior.REPLACE
    assert ("Dark Coldbrew", "Medium Coldbrew") in log["replaced"]


@pytest.mark.django_db
def test_dirty_chai_replaces_and_adds(ingredient_types):
    milk_type = ingredient_types["MILK"]
    extra_type = ingredient_types["EXTRA"]
    milk = Ingredient.objects.create(name="Whole Milk", type=milk_type)
    chai = Ingredient.objects.create(name="Chai Milk Blend", type=milk_type)
    espresso_ing = Ingredient.objects.create(name="Espresso Shot", type=extra_type)

    espresso_mod = RecipeModifier.objects.create(
        name="Add Espresso",
        ingredient_type=extra_type,
        behavior=ModifierBehavior.ADD,
        ingredient=espresso_ing,
        base_quantity=1,
        unit="shot",
    )

    modifier = RecipeModifier.objects.create(
        name="Dirty Chai",
        ingredient_type=milk_type,
        behavior=ModifierBehavior.REPLACE,
        ingredient=chai,
        base_quantity=1,
        unit="oz",
        target_selector={"by_type": [milk_type.id]},
        replaces={"to": [["Chai Milk Blend", 1.0]]},
    )
    modifier.expands_to.add(espresso_mod)

    recipe_map = {"Whole Milk": _recipe_entry("8.0", milk_type)}
    result, log = handle_extras("Dirty Chai", recipe_map, [])

    assert "Chai Milk Blend" in result
    assert "Espresso Shot" in result
    assert log["behavior"] == ModifierBehavior.REPLACE
    assert any("Chai Milk Blend" in pair for pair in log["replaced"])


@pytest.mark.django_db
def test_baristas_choice_modifier_expands_recipe(ingredient_types):
    coffee_type = ingredient_types["COFFEE"]
    milk_type = ingredient_types["MILK"]
    flavor_type = ingredient_types["FLAVOR"]
    espresso = Ingredient.objects.create(name="Espresso Shot", type=coffee_type)
    milk = Ingredient.objects.create(name="Whole Milk", type=milk_type)
    maple_syrup = Ingredient.objects.create(name="Maple Syrup", type=flavor_type)
    vanilla = Ingredient.objects.create(name="Vanilla Bean", type=flavor_type)

    baristas_choice = Category.objects.create(name="Barista's Choice")
    maple_recipe = Product.objects.create(name="Maple Cookie Latte", sku="maple-cookie")
    maple_recipe.categories.add(baristas_choice)
    RecipeItem.objects.create(product=maple_recipe, ingredient=maple_syrup, quantity=Decimal("1.5"))
    RecipeItem.objects.create(product=maple_recipe, ingredient=vanilla, quantity=Decimal("0.5"))

    base_recipe_map = {
        "Espresso Shot": _recipe_entry("2.0", coffee_type),
        "Whole Milk": _recipe_entry("8.0", milk_type),
    }

    result, log = handle_extras(
        "Maple Cookie",
        base_recipe_map,
        normalized_modifiers=["maple cookie"],
        recipe_context=list(base_recipe_map.keys()),
    )

    assert set(["Espresso Shot", "Whole Milk"]).issubset(result.keys())
    assert result["Maple Syrup"]["qty"] == Decimal("1.5")
    assert result["Maple Syrup"]["type_id"] == flavor_type.id
    assert result["Vanilla Bean"]["qty"] == Decimal("0.5")
    assert result["Vanilla Bean"]["type_id"] == flavor_type.id
    assert log["behavior"] == "expand_baristas_choice"
    assert log["source_recipe"] == "Maple Cookie Latte"


@pytest.mark.django_db
def test_handle_extras_with_invalid_json(ingredient_types):
    milk_type = ingredient_types["MILK"]
    milk = Ingredient.objects.create(name="Whole Milk", type=milk_type)
    RecipeModifier.objects.create(
        name="Bad Modifier",
        ingredient_type=milk_type,
        behavior=ModifierBehavior.SCALE,
        ingredient=milk,
        base_quantity=1,
        unit="oz",
        target_selector="not a json object",
    )

    recipe_map = {"Whole Milk": _recipe_entry("8.0", milk_type)}
    try:
        result, log = handle_extras("Bad Modifier", recipe_map, [])
    except Exception as exc:  # pragma: no cover - defensive
        pytest.fail(f"handle_extras raised unexpected exception: {exc}")

    assert isinstance(result, dict)
    assert isinstance(log, dict)
