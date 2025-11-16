from decimal import Decimal
from types import SimpleNamespace

import pytest

from django.utils import timezone

from importers._aggregate_usage import aggregate_ingredient_usage, infer_temp_and_size
from mscrInventory.models import (
    ContainerType,
    Ingredient,
    IngredientType,
    IngredientUsageLog,
    ModifierBehavior,
    Packaging,
    RecipeModifier,
    SizeLabel,
    UnitType,
)


@pytest.mark.django_db
def test_infer_temp_and_size_detects_growler_from_name():
    SizeLabel.objects.create(label="growler")
    temp, size = infer_temp_and_size("Cold Brew Growler")
    assert temp == "cold"
    assert size == "growler"


@pytest.mark.django_db
def test_infer_temp_and_size_detects_capacity_match_from_descriptor():
    fluid_oz = UnitType.objects.create(name="Fluid Ounce", abbreviation="fl oz")
    each = UnitType.objects.create(name="Each", abbreviation="ea")
    packaging_type = IngredientType.objects.create(name="Packaging")
    SizeLabel.objects.create(label="growler")
    container = ContainerType.objects.create(
        name="64oz Growler",
        capacity=Decimal("64.0"),
        unit_type=fluid_oz,
    )
    packaging = Packaging.objects.create(
        name="64oz Growler",
        type=packaging_type,
        unit_type=each,
        container=container,
        temp="cold",
        multiplier=4.0,
    )
    packaging.size_labels.add(SizeLabel.objects.get(label="growler"))

    temp, size = infer_temp_and_size("Cold Brew", ["64oz"])
    assert temp == "cold"
    assert size == "growler"


@pytest.mark.django_db
def test_infer_temp_and_size_defaults_to_smallest_size_when_unknown():
    fluid_oz = UnitType.objects.create(name="Fluid Ounce", abbreviation="fl oz")
    each = UnitType.objects.create(name="Each", abbreviation="ea")
    packaging_type = IngredientType.objects.create(name="Packaging")
    small = SizeLabel.objects.create(label="small")
    xl = SizeLabel.objects.create(label="XL")

    small_container = ContainerType.objects.create(
        name="12oz Hot Cup",
        capacity=Decimal("12.0"),
        unit_type=fluid_oz,
    )
    large_container = ContainerType.objects.create(
        name="32oz Cold Cup",
        capacity=Decimal("32.0"),
        unit_type=fluid_oz,
    )

    small_packaging = Packaging.objects.create(
        name="12oz Hot Cup",
        type=packaging_type,
        unit_type=each,
        container=small_container,
        temp="hot",
        multiplier=1.0,
    )
    small_packaging.size_labels.add(small)

    large_packaging = Packaging.objects.create(
        name="32oz Cold Cup",
        type=packaging_type,
        unit_type=each,
        container=large_container,
        temp="cold",
        multiplier=2.0,
    )
    large_packaging.size_labels.add(xl)

    temp, size = infer_temp_and_size("Latte")
    assert temp == "hot"
    assert size == "small"


@pytest.mark.django_db
def test_aggregate_usage_uses_packaging_multiplier_and_capacity():
    fluid_oz = UnitType.objects.create(name="Fluid Ounce", abbreviation="fl oz")
    each = UnitType.objects.create(name="Each", abbreviation="ea")
    packaging_type = IngredientType.objects.create(name="Packaging")
    beverage_type = IngredientType.objects.create(name="Beverage")
    espresso_type = IngredientType.objects.create(name="Espresso")
    espresso_type.unit_type = "unit"

    size_label = SizeLabel.objects.create(label="XL")
    container = ContainerType.objects.create(
        name="32oz Cold Cup",
        capacity=Decimal("32.0"),
        unit_type=fluid_oz,
    )
    packaging = Packaging.objects.create(
        name="32oz Cold Cup",
        type=packaging_type,
        unit_type=each,
        container=container,
        temp="cold",
        multiplier=2.0,
    )
    packaging.size_labels.add(size_label)

    cold_brew = Ingredient.objects.create(
        name="Cold Brew Base",
        type=beverage_type,
        unit_type=fluid_oz,
    )
    milk = Ingredient.objects.create(
        name="Whole Milk",
        type=beverage_type,
        unit_type=fluid_oz,
    )
    espresso = Ingredient.objects.create(
        name="Espresso Shot",
        type=espresso_type,
        unit_type=each,
    )

    recipe_items = [
        SimpleNamespace(ingredient=cold_brew, quantity=Decimal("10.0")),
        SimpleNamespace(ingredient=milk, quantity=Decimal("4.0")),
        SimpleNamespace(ingredient=espresso, quantity=Decimal("1.0")),
    ]

    usage = aggregate_ingredient_usage(
        recipe_items,
        temp_type="cold",
        size="xl",
        is_drink=True,
        include_cup=True,
    )

    assert usage["32oz Cold Cup"]["qty"] == Decimal("1")
    assert "packaging" in usage["32oz Cold Cup"]["sources"]

    assert usage["Espresso Shot"]["qty"] == Decimal("2")
    assert usage["Whole Milk"]["qty"] == Decimal("8")
    assert usage["Cold Brew Base"]["qty"] == Decimal("24")


@pytest.mark.django_db
def test_catering_platter_uses_recent_popular_variants():
    each = UnitType.objects.create(name="Each", abbreviation="ea")
    baked_type = IngredientType.objects.create(name="Baked Good")

    corn = Ingredient.objects.create(name="Corn Muffin", type=baked_type, unit_type=each)
    blueberry = Ingredient.objects.create(name="Blueberry Muffin", type=baked_type, unit_type=each)
    banana = Ingredient.objects.create(name="Banana Nut Muffin", type=baked_type, unit_type=each)

    today = timezone.now().date()
    IngredientUsageLog.objects.create(
        ingredient=corn,
        date=today,
        quantity_used=Decimal("30"),
        source="square",
    )
    IngredientUsageLog.objects.create(
        ingredient=blueberry,
        date=today,
        quantity_used=Decimal("20"),
        source="square",
    )
    IngredientUsageLog.objects.create(
        ingredient=banana,
        date=today,
        quantity_used=Decimal("10"),
        source="square",
    )

    usage = aggregate_ingredient_usage(
        [],
        temp_type=None,
        size=None,
        is_drink=False,
        include_cup=False,
        modifier_tokens=["6 muffins platter", "catering platter"],
    )

    assert usage["Corn Muffin"]["qty"] == Decimal("3")
    assert usage["Blueberry Muffin"]["qty"] == Decimal("2")
    assert usage["Banana Nut Muffin"]["qty"] == Decimal("1")
    assert usage["Corn Muffin"]["sources"] == ["catering_platter"]


@pytest.mark.django_db
def test_aggregate_usage_includes_packaging_expands_items():
    fluid_oz = UnitType.objects.create(name="Fluid Ounce", abbreviation="fl oz")
    each = UnitType.objects.create(name="Each", abbreviation="ea")
    packaging_type = IngredientType.objects.create(name="Packaging")
    size_label = SizeLabel.objects.create(label="catering box")

    container = ContainerType.objects.create(
        name="Catering Hot and Cold Box 96oz",
        capacity=Decimal("96.0"),
        unit_type=fluid_oz,
    )
    packaging = Packaging.objects.create(
        name="Catering Hot and Cold Box",
        type=packaging_type,
        unit_type=each,
        container=container,
        temp="both",
        multiplier=Decimal("8.0"),
    )
    packaging.size_labels.add(size_label)

    milk_whole = Ingredient.objects.create(
        name="10oz Whole Milk Container",
        type=packaging_type,
        unit_type=each,
    )
    milk_oat = Ingredient.objects.create(
        name="10oz Oat Milk Container",
        type=packaging_type,
        unit_type=each,
    )
    milk_almond = Ingredient.objects.create(
        name="10oz Almond Milk Container",
        type=packaging_type,
        unit_type=each,
    )
    packaging.expands_to.add(milk_whole, milk_oat, milk_almond)

    usage = aggregate_ingredient_usage(
        [],
        temp_type="hot",
        size="catering box",
        is_drink=True,
        include_cup=True,
    )

    assert usage["Catering Hot and Cold Box"]["qty"] == Decimal("1")
    assert usage["Catering Hot and Cold Box"]["sources"] == ["packaging"]

    for milk_name in (
        "10oz Whole Milk Container",
        "10oz Oat Milk Container",
        "10oz Almond Milk Container",
    ):
        assert usage[milk_name]["qty"] == Decimal("1")
        assert usage[milk_name]["sources"] == ["packaging_expands"]


@pytest.mark.django_db
def test_keg_size_scales_liquid_usage_to_capacity():
    fluid_oz = UnitType.objects.create(name="Fluid Ounce", abbreviation="fl oz")
    each = UnitType.objects.create(name="Each", abbreviation="ea")
    packaging_type = IngredientType.objects.create(name="Packaging")
    beverage_type = IngredientType.objects.create(name="Beverage Component")

    small_label = SizeLabel.objects.create(label="small")
    keg_label = SizeLabel.objects.create(label="keg")

    small_container = ContainerType.objects.create(
        name="12oz Cup",
        capacity=Decimal("12.0"),
        unit_type=fluid_oz,
    )
    keg_container = ContainerType.objects.create(
        name="Cold Brew Keg",
        capacity=Decimal("640.0"),
        unit_type=fluid_oz,
    )

    small_packaging = Packaging.objects.create(
        name="12oz Cold Cup",
        type=packaging_type,
        unit_type=each,
        container=small_container,
        temp="cold",
        multiplier=Decimal("1.0"),
    )
    small_packaging.size_labels.add(small_label)

    keg_packaging = Packaging.objects.create(
        name="Retail Keg",
        type=packaging_type,
        unit_type=each,
        container=keg_container,
        temp="cold",
        multiplier=Decimal("1.0"),
    )
    keg_packaging.size_labels.add(keg_label)

    coldbrew = Ingredient.objects.create(
        name="Cold Brew",
        type=beverage_type,
        unit_type=fluid_oz,
    )

    keg_modifier = RecipeModifier.objects.create(
        name="cold brew keg",
        ingredient_type=beverage_type,
        behavior=ModifierBehavior.ADD,
        ingredient=coldbrew,
        base_quantity=Decimal("12.0"),
        unit="fl_oz",
    )

    usage = aggregate_ingredient_usage(
        [],
        resolved_modifiers=[keg_modifier],
        temp_type="cold",
        size="keg",
        is_drink=True,
        include_cup=False,
    )

    assert usage["Cold Brew"]["qty"] == Decimal("640")
