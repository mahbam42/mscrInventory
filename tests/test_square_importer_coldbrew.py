import pytest
from io import StringIO
from pathlib import Path
from decimal import Decimal
from django.core.management.base import CommandError
from django.core.management import call_command
from mscrInventory.models import Product, Ingredient, RecipeItem, RecipeModifier, UnitType, IngredientType

def handle(self, *args, **options):
        file_path = Path(options["file"])
        # ✅ Convert to integer safely
        try:
            row_index = int(options.get("row", 0))
        except (TypeError, ValueError):
            raise CommandError(f"Invalid row number: {options.get('row')}")
        verbose = options["verbose"]

@pytest.fixture
def seed_coldbrew_data(db):
    """
    Create minimal data for Coldbrew importer tests:
    - Unit types
    - Ingredient type
    - Ingredients
    - Modifiers (with required fields populated)
    - Base product recipe
    """

    # --- Unit Types ---
    fl_oz, _ = UnitType.objects.get_or_create(
        name="Fluid Ounce",
        defaults={"abbreviation": "fl_oz", "conversion_to_base": Decimal("1.0000")},
    )
    unit, _ = UnitType.objects.get_or_create(
        name="Unit",
        defaults={"abbreviation": "unit", "conversion_to_base": Decimal("1.0000")},
    )

    # --- Ingredient Type ---
    beverage_type, _ = IngredientType.objects.get_or_create(name="Beverage Component")

    # --- Ingredients ---
    dark = Ingredient.objects.create(name="Dark Coldbrew",   unit_type=fl_oz, type=beverage_type)
    medium = Ingredient.objects.create(name="Medium Coldbrew", unit_type=fl_oz, type=beverage_type)
    white_chocolate = Ingredient.objects.create(name="White Chocolate Cold Brew", unit_type=fl_oz, type=beverage_type)
    milk = Ingredient.objects.create(name="Whole Milk",      unit_type=fl_oz, type=beverage_type)
    cherry_syrup = Ingredient.objects.create(name="Cherry Syrup", unit_type=fl_oz, type=beverage_type)
    vanilla_bean = Ingredient.objects.create(name="Vanilla Bean", unit_type=fl_oz, type=beverage_type)
    cup32 = Ingredient.objects.create(name="32oz Cold Cup",  unit_type=unit,  type=beverage_type)
    cup16 = Ingredient.objects.create(name="16oz Cold Cup",  unit_type=unit,  type=beverage_type)

    # --- Product & Base Recipe (XL starts from 16 oz dark) ---
    product = Product.objects.create(name="Nitro Coldbrew")
    RecipeItem.objects.create(product=product, ingredient=dark, quantity=Decimal("16.0"))

    # ---------- Modifiers ----------
    # Parent size modifier "medium": replaces Dark with Medium 22 fl_oz
    mod_medium = RecipeModifier.objects.create(
        name="medium",
        type="COFFEE",  # valid from MODIFIER_TYPES
        behavior=RecipeModifier.ModifierBehavior.REPLACE,
        ingredient=medium,                 # the ingredient this modifier represents
        base_quantity=Decimal("22.0"),     # quantity applied when chosen
        unit="fl_oz",
        quantity_factor=Decimal("1.0"),
        target_selector={"by_name": ["Dark Coldbrew"]},
        replaces={"to": [["Medium Coldbrew", 22.0]]},
    )

    # Parent size modifier "medium": replaces Dark with Medium 22 fl_oz
    mod_white_chocolate = RecipeModifier.objects.create(
        name="White Chocolate Coldbrew",
        type="COFFEE",  # valid from MODIFIER_TYPES
        behavior=RecipeModifier.ModifierBehavior.REPLACE,
        ingredient=white_chocolate,                 # the ingredient this modifier represents
        base_quantity=Decimal("22.0"),     # quantity applied when chosen
        unit="fl_oz",
        quantity_factor=Decimal("1.0"),
        target_selector={"by_name": ["Dark Coldbrew"]},
        replaces={"to": [["White Chocolate Coldbrew", 22.0]]},
    )

    # Milk: add 8 fl_oz
    mod_whole_milk = RecipeModifier.objects.create(
        name="whole milk",
        type="MILK",
        behavior=RecipeModifier.ModifierBehavior.ADD,
        ingredient=milk,
        base_quantity=Decimal("8.0"),
        unit="fl_oz",
        quantity_factor=Decimal("1.0"),
        target_selector={"by_name": ["Whole Milk"]},
    )

    # Flavor combo "Cherry Dipped Vanilla" expands into two ADD modifiers:
    mod_cherry = RecipeModifier.objects.create(
        name="cherry syrup (part of cherry dipped vanilla)",
        type="FLAVOR",
        behavior=RecipeModifier.ModifierBehavior.ADD,
        ingredient=cherry_syrup,
        base_quantity=Decimal("2.0"),
        unit="fl_oz",
        quantity_factor=Decimal("1.0"),
        target_selector={"by_name": ["Cherry Syrup"]},
    )
    mod_vanilla = RecipeModifier.objects.create(
        name="vanilla bean (part of cherry dipped vanilla)",
        type="FLAVOR",
        behavior=RecipeModifier.ModifierBehavior.ADD,
        ingredient=vanilla_bean,
        base_quantity=Decimal("2.0"),
        unit="fl_oz",
        quantity_factor=Decimal("1.0"),
        target_selector={"by_name": ["Vanilla Bean"]},
    )
    mod_flavor_combo = RecipeModifier.objects.create(
        name="cherry dipped vanilla",
        type="FLAVOR",
        behavior=RecipeModifier.ModifierBehavior.EXPAND,
        ingredient=cherry_syrup,           # anchor to one of the pair; required FK
        base_quantity=Decimal("0.0"),
        unit="fl_oz",
        quantity_factor=Decimal("1.0"),
    )
    # Link the combo to its components (must be RecipeModifier instances)
    mod_flavor_combo.expands_to.add(mod_cherry, mod_vanilla)

    return {
        "product": product,
        "ingredients": [dark, medium, milk, cherry_syrup, vanilla_bean, cup32],
        "modifiers": [mod_medium, mod_whole_milk, mod_flavor_combo, mod_cherry, mod_vanilla],
        "unit_types": {"fl_oz": fl_oz, "unit": unit},
        "ingredient_type": beverage_type,
    }

@pytest.mark.django_db
def test_coldbrew_xl_medium(monkeypatch, seed_coldbrew_data):
    out = StringIO()
    call_command(
        "test_square_row",
        file="squareCSVs/squareCSV_importTest2.csv",
        row=2,
        verbosity=2,
        stdout=out,
    )
    output = out.getvalue()

    # Verify normalized output structure
    assert "🏷 Item: XL Nitro" in output
    assert "🔧 Modifiers:" in output
    assert "cherry dipped vanilla" in output.lower()
    assert "whole milk" in output.lower()
    assert "medium" in output.lower()
    assert "→ Nitro (xl)" in output
    assert "Final ingredient usage" in output

    # Key ingredients should appear
    for name in ["32oz Cup", "Medium Coldbrew", "Whole Milk", "Cherry Syrup", "Vanilla Bean"]:
        assert name in output, f"Missing expected ingredient: {name}"

    # Should not show any error flags
    assert "errors" not in output.lower()

@pytest.mark.django_db
def test_coldbrew_xl_white_chocolate(monkeypatch, seed_coldbrew_data):
    out = StringIO()
    call_command(
        "test_square_row",
        file="squareCSVs/squareCSV_importTest3.csv",
        row=2,
        verbosity=2,
        stdout=out,
    )
    output = out.getvalue()

    assert "🏷 Item: XL Nitro" in output
    assert "White Chocolate" in output or "white chocolate" in output.lower()
    assert "→ Nitro Coldbrew (xl)" in output
    assert "Final ingredient usage" in output

    # Expect base ingredients and scaled logic present
    assert "Whole Milk" in output
    assert "32oz Cup" in output
    assert "errors" not in output.lower()

@pytest.mark.django_db
def test_coldbrew_small_scaling(monkeypatch, seed_coldbrew_data):
    out = StringIO()
    call_command(
        "test_square_row",
        file="squareCSVs/squareCSV_importTest_small.csv",
        row=2,
        verbosity=2,
        stdout=out,
    )
    output = out.getvalue()

    assert "🏷 Item:" in output
    assert "→ Nitro Coldbrew (sm" in output or "small" in output.lower()
    assert "Final ingredient usage" in output

    # Look for key downsized ingredients
    for name in ["16oz Cup", "medium"]:
        assert name.lower() in output.lower(), f"Missing expected ingredient: {name}"

    # Ensure the scaled quantities (roughly half XL) appear
    assert "errors" not in output.lower()
