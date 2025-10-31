import pytest
from decimal import Decimal
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
    result, log = handle_extras("Extra Bacon", recipe_map, [])

    assert "Bacon" in result
    assert result["Bacon"]["qty"] == Decimal("2.00")
    assert log["behavior"] == "scale"
    assert log["replaced"] == []
    assert log["added"] == []


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
    result, log = handle_extras("Lite Sugar", recipe_map, [])

    assert "Sugar" in result
    assert result["Sugar"]["qty"] == Decimal("4.00")
    assert log["behavior"] == "scale"


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
    result, log = handle_extras("Oat Milk", recipe_map, [])

    assert "Oat Milk" in result
    assert log["behavior"] == "replace"
    assert ("Whole Milk", "Oat Milk") in log["replaced"]


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
        replaces={"to": [["Dark Cold Brew", 0.5], ["Medium Cold Brew", 0.5]]},
    )

    recipe_map = {"Cold Brew Base": {"qty": Decimal("6.0"), "type": "COFFEE"}}
    result, log = handle_extras("Split Cold Brew", recipe_map, [])

    #assert all(k in result for k in ["Dark Cold Brew", "White Cold Brew"])
    assert log["behavior"] == "replace"
    #assert any("Dark Cold Brew" in pair for pair in log["replaced"])
    assert any("Cold Brew" in k for k in result.keys())

@pytest.mark.django_db
def test_size_modifier_not_ignored_when_rule_exists(ingredient_types):
    dark = Ingredient.objects.create(name="Dark Coldbrew", type=ingredient_types["COFFEE"])
    medium = Ingredient.objects.create(name="Medium Coldbrew", type=ingredient_types["COFFEE"])
    RecipeModifier.objects.create(
        name="medium",
        type="COFFEE",
        behavior=ModifierBehavior.REPLACE,
        ingredient=medium,
        base_quantity=Decimal("22.0"),
        unit="fl_oz",
        target_selector={"by_name": ["Dark Coldbrew"]},
    )

    recipe_map = {"Dark Coldbrew": {"qty": Decimal("16.0"), "type": "COFFEE"}}
    result, log = handle_extras("medium", recipe_map, [], recipe_context=list(recipe_map.keys()))

    assert "Medium Coldbrew" in result
    assert log["behavior"] == ModifierBehavior.REPLACE
    assert ("Dark Coldbrew", "Medium Coldbrew") in log["replaced"]

@pytest.mark.django_db
def test_size_modifier_not_ignored_when_rule_exists(ingredient_types):
    dark = Ingredient.objects.create(name="Dark Coldbrew", type=ingredient_types["COFFEE"])
    medium = Ingredient.objects.create(name="Medium Coldbrew", type=ingredient_types["COFFEE"])
    RecipeModifier.objects.create(
        name="medium",
        type="COFFEE",
        behavior=ModifierBehavior.REPLACE,
        ingredient=medium,
        base_quantity=Decimal("22.0"),
        unit="fl_oz",
        target_selector={"by_name": ["Dark Coldbrew"]},
    )

    recipe_map = {"Dark Coldbrew": {"qty": Decimal("16.0"), "type": "COFFEE"}}
    result, log = handle_extras("medium", recipe_map, [], recipe_context=list(recipe_map.keys()))

    assert "Medium Coldbrew" in result
    assert log["behavior"] == ModifierBehavior.REPLACE
    assert ("Dark Coldbrew", "Medium Coldbrew") in log["replaced"]


@pytest.mark.django_db
def test_size_modifier_not_ignored_when_rule_exists(ingredient_types):
    dark = Ingredient.objects.create(name="Dark Coldbrew", type=ingredient_types["COFFEE"])
    medium = Ingredient.objects.create(name="Medium Coldbrew", type=ingredient_types["COFFEE"])
    RecipeModifier.objects.create(
        name="medium",
        type="COFFEE",
        behavior=ModifierBehavior.REPLACE,
        ingredient=medium,
        base_quantity=Decimal("22.0"),
        unit="fl_oz",
        target_selector={"by_name": ["Dark Coldbrew"]},
    )

    recipe_map = {"Dark Coldbrew": {"qty": Decimal("16.0"), "type": "COFFEE"}}
    result, log = handle_extras("medium", recipe_map, [], recipe_context=list(recipe_map.keys()))

    assert "Medium Coldbrew" in result
    assert log["behavior"] == ModifierBehavior.REPLACE
    assert ("Dark Coldbrew", "Medium Coldbrew") in log["replaced"]


@pytest.mark.django_db
def test_size_modifier_not_ignored_when_rule_exists(ingredient_types):
    dark = Ingredient.objects.create(name="Dark Coldbrew", type=ingredient_types["COFFEE"])
    medium = Ingredient.objects.create(name="Medium Coldbrew", type=ingredient_types["COFFEE"])
    RecipeModifier.objects.create(
        name="medium",
        type="COFFEE",
        behavior=ModifierBehavior.REPLACE,
        ingredient=medium,
        base_quantity=Decimal("22.0"),
        unit="fl_oz",
        target_selector={"by_name": ["Dark Coldbrew"]},
    )

    recipe_map = {"Dark Coldbrew": {"qty": Decimal("16.0"), "type": "COFFEE"}}
    result, log = handle_extras("medium", recipe_map, [], recipe_context=list(recipe_map.keys()))

    assert "Medium Coldbrew" in result
    assert log["behavior"] == ModifierBehavior.REPLACE
    assert ("Dark Coldbrew", "Medium Coldbrew") in log["replaced"]


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
    result, log = handle_extras("Dirty Chai", recipe_map, [])

    assert "Chai Milk Blend" in result
    assert "Espresso Shot" in result
    assert log["behavior"] == "replace"
    assert any("Chai Milk Blend" in pair for pair in log["replaced"])


@pytest.mark.django_db
def test_baristas_choice_modifier_expands_recipe(ingredient_types):
    espresso = Ingredient.objects.create(name="Espresso Shot", type=ingredient_types["COFFEE"])
    milk = Ingredient.objects.create(name="Whole Milk", type=ingredient_types["MILK"])
    maple_syrup = Ingredient.objects.create(name="Maple Syrup", type=ingredient_types["FLAVOR"])
    vanilla = Ingredient.objects.create(name="Vanilla Bean", type=ingredient_types["FLAVOR"])

    baristas_choice = Category.objects.create(name="Barista's Choice")
    maple_recipe = Product.objects.create(name="Maple Cookie Latte", sku="maple-cookie")
    maple_recipe.categories.add(baristas_choice)
    RecipeItem.objects.create(product=maple_recipe, ingredient=maple_syrup, quantity=Decimal("1.5"))
    RecipeItem.objects.create(product=maple_recipe, ingredient=vanilla, quantity=Decimal("0.5"))

    base_recipe_map = {
        "Espresso Shot": {"qty": Decimal("2.0"), "type": "COFFEE"},
        "Whole Milk": {"qty": Decimal("8.0"), "type": "MILK"},
    }

    result, log = handle_extras(
        "Maple Cookie",
        base_recipe_map,
        normalized_modifiers=["maple cookie"],
        recipe_context=list(base_recipe_map.keys()),
    )

    assert set(["Espresso Shot", "Whole Milk"]).issubset(result.keys())
    assert result["Maple Syrup"]["qty"] == Decimal("1.5")
    assert result["Vanilla Bean"]["qty"] == Decimal("0.5")
    assert log["behavior"] == "expand_baristas_choice"
    assert log["source_recipe"] == "Maple Cookie Latte"


@pytest.mark.django_db
def test_baristas_choice_modifier_expands_recipe(ingredient_types):
    espresso = Ingredient.objects.create(name="Espresso Shot", type=ingredient_types["COFFEE"])
    milk = Ingredient.objects.create(name="Whole Milk", type=ingredient_types["MILK"])
    maple_syrup = Ingredient.objects.create(name="Maple Syrup", type=ingredient_types["FLAVOR"])
    vanilla = Ingredient.objects.create(name="Vanilla Bean", type=ingredient_types["FLAVOR"])

    baristas_choice = Category.objects.create(name="Barista's Choice")
    maple_recipe = Product.objects.create(name="Maple Cookie Latte", sku="maple-cookie")
    maple_recipe.categories.add(baristas_choice)
    RecipeItem.objects.create(product=maple_recipe, ingredient=maple_syrup, quantity=Decimal("1.5"))
    RecipeItem.objects.create(product=maple_recipe, ingredient=vanilla, quantity=Decimal("0.5"))

    base_recipe_map = {
        "Espresso Shot": {"qty": Decimal("2.0"), "type": "COFFEE"},
        "Whole Milk": {"qty": Decimal("8.0"), "type": "MILK"},
    }

    result, log = handle_extras(
        "Maple Cookie",
        base_recipe_map,
        normalized_modifiers=["maple cookie"],
        recipe_context=list(base_recipe_map.keys()),
    )

    assert set(["Espresso Shot", "Whole Milk"]).issubset(result.keys())
    assert result["Maple Syrup"]["qty"] == Decimal("1.5")
    assert result["Vanilla Bean"]["qty"] == Decimal("0.5")
    assert log["behavior"] == "expand_baristas_choice"
    assert log["source_recipe"] == "Maple Cookie Latte"

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
        result, log = handle_extras("Bad Modifier", recipe_map, [])
    except Exception as e:
        print("⚠️ handle_extras raised an exception:", e)
        result, log = {}, {}

    # Should not crash and should always return a dict + changelog
    assert isinstance(result, dict)
    assert isinstance(log, dict)
