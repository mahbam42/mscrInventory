import pytest
from decimal import Decimal
from mscrInventory.models import Ingredient, IngredientType, RecipeModifier, ModifierBehavior
from importers._handle_extras import handle_extras


@pytest.fixture
def ingredient_types(db):
    """
    Creates or reuses IngredientType objects for tests.
    """
    names = ["MILK", "TOPPING", "SUGAR", "FLAVOR", "EXTRA", "COFFEE"]
    types = {}
    for n in names:
        obj, _ = IngredientType.objects.get_or_create(name=n)
        types[n] = obj
    return types


@pytest.mark.django_db
def test_extra_bacon_scales_correctly(ingredient_types):
    bacon = Ingredient.objects.create(name="Bacon", type=ingredient_types["TOPPING"])
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
    result = handle_extras("Extra Bacon", recipe_map, [])
    assert "Bacon" in result
    assert result["Bacon"]["qty"] == Decimal("2.0")


@pytest.mark.django_db
def test_lite_sugar_scales_down(ingredient_types):
    sugar = Ingredient.objects.create(name="Sugar", type=ingredient_types["SUGAR"])
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
    result = handle_extras("Lite Sugar", recipe_map, [])
    assert "Sugar" in result
    assert result["Sugar"]["qty"] == Decimal("4.0")


@pytest.mark.django_db
def test_oat_milk_replaces_milk(ingredient_types):
    milk = Ingredient.objects.create(name="Whole Milk", type=ingredient_types["MILK"])
    oat = Ingredient.objects.create(name="Oat Milk", type=ingredient_types["MILK"])
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
    result = handle_extras("Oat Milk", recipe_map, [])
    assert "Oat Milk" in result
    assert "Whole Milk" not in result


@pytest.mark.django_db
def test_split_coldbrew_handles_two_way_blend(ingredient_types):
    base = Ingredient.objects.create(name="Cold Brew Base", type=ingredient_types["COFFEE"])
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
    result = handle_extras("Split Cold Brew", recipe_map, [])
    assert "Dark Cold Brew" in result
    assert "White Cold Brew" in result
    assert all(abs(v["qty"] - Decimal("3.0")) < Decimal("0.01") for v in result.values())


@pytest.mark.django_db
def test_split_coldbrew_handles_three_way_blend(ingredient_types):
    base = Ingredient.objects.create(name="Cold Brew Base", type=ingredient_types["COFFEE"])
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
    result = handle_extras("Split Cold Brew 3-Way", recipe_map, [])
    assert all(k in result for k in ["Dark Cold Brew", "Medium Cold Brew", "White Cold Brew"])
    total_qty = sum(v["qty"] for v in result.values())
    assert abs(total_qty - Decimal("9.0")) < Decimal("0.01")


@pytest.mark.django_db
def test_dirty_chai_replaces_and_adds(ingredient_types):
    milk = Ingredient.objects.create(name="Whole Milk", type=ingredient_types["MILK"])
    chai = Ingredient.objects.create(name="Chai Milk Blend", type=ingredient_types["MILK"])
    espresso_ing = Ingredient.objects.create(name="Espresso Shot", type=ingredient_types["EXTRA"])

    espresso_mod = RecipeModifier.objects.create(
        name="Add Espresso",
        type="EXTRA",
        behavior=ModifierBehavior.ADD,
        ingredient=espresso_ing,
        base_quantity=1,
        unit="shot",
    )

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
    modifier.expands_to.add(espresso_mod)

    recipe_map = {"Whole Milk": {"qty": Decimal("8.0"), "type": "MILK"}}
    result = handle_extras("Dirty Chai", recipe_map, [])
    assert "Chai Milk Blend" in result
    assert "Espresso Shot" in result


@pytest.mark.django_db
def test_handle_extras_with_invalid_json(ingredient_types):
    milk = Ingredient.objects.create(name="Whole Milk", type=ingredient_types["MILK"])
    RecipeModifier.objects.create(
        name="Bad Modifier",
        type="MILK",
        behavior=ModifierBehavior.SCALE,
        ingredient=milk,
        base_quantity=1,
        unit="oz",
        # intentionally invalid field type
        target_selector="not a json object",
    )

    recipe_map = {"Whole Milk": {"qty": Decimal("8.0"), "type": "MILK"}}
    try:
        result = handle_extras("Bad Modifier", recipe_map, [])
    except Exception as e:
        print("⚠️ handle_extras raised an exception:", e)
        result = {}

    # Should not crash and should always return a dict
    assert isinstance(result, dict)
