import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from mscrInventory.management.commands.sync_orders import write_usage_logs
from mscrInventory.models import (
    Category,
    Ingredient,
    IngredientType,
    IngredientUsageLog,
    Order,
    OrderItem,
    Product,
    RecipeItem,
    RecipeModifier,
    StockEntry,
    UnitType,
)
from tests.factories import IngredientFactory
from mscrInventory.utils import reports


@pytest.mark.django_db
def test_reporting_aggregations():
    report_date = datetime.date(2024, 1, 2)
    order_dt = timezone.make_aware(datetime.datetime(2024, 1, 2, 9, 0))

    coffee_cat = Category.objects.create(name="Coffee")
    seasonal_cat = Category.objects.create(name="Seasonal")

    milk_type = IngredientType.objects.create(name="Milk Base")
    syrup_type = IngredientType.objects.create(name="Syrup")
    espresso_type = IngredientType.objects.create(name="Espresso")

    milk = Ingredient.objects.create(
        name="Milk",
        type=milk_type,
        average_cost_per_unit=Decimal("1.00"),
        current_stock=Decimal("100"),
    )
    syrup = Ingredient.objects.create(
        name="Pumpkin Syrup",
        type=syrup_type,
        average_cost_per_unit=Decimal("0.00"),
        current_stock=Decimal("50"),
    )
    oat_milk = Ingredient.objects.create(
        name="Oat Milk",
        type=milk_type,
        average_cost_per_unit=Decimal("1.20"),
        current_stock=Decimal("40"),
    )
    pumpkin_spice_syrup = Ingredient.objects.create(
        name="Pumpkin Spice Syrup",
        type=syrup_type,
        average_cost_per_unit=Decimal("0.50"),
        current_stock=Decimal("30"),
    )
    dark_cold_brew = Ingredient.objects.create(
        name="Dark Cold Brew",
        type=espresso_type,
        average_cost_per_unit=Decimal("0.60"),
        current_stock=Decimal("25"),
    )

    RecipeModifier.objects.create(
        name="oat milk",
        ingredient_type=milk_type,
        ingredient=oat_milk,
        base_quantity=Decimal("8.00"),
        unit="oz",
        cost_per_unit=Decimal("0.00"),
        price_per_unit=Decimal("0.00"),
    )
    RecipeModifier.objects.create(
        name="pumpkin spice",
        ingredient_type=syrup_type,
        ingredient=pumpkin_spice_syrup,
        base_quantity=Decimal("0.50"),
        unit="pump",
        cost_per_unit=Decimal("0.00"),
        price_per_unit=Decimal("0.00"),
    )
    RecipeModifier.objects.create(
        name="extra shot",
        ingredient_type=espresso_type,
        ingredient=dark_cold_brew,
        base_quantity=Decimal("1.00"),
        unit="shot",
        cost_per_unit=Decimal("0.00"),
        price_per_unit=Decimal("0.00"),
    )

    latte = Product.objects.create(name="Latte", sku="LATTE-12")
    latte.categories.add(coffee_cat, seasonal_cat)
    RecipeItem.objects.create(
        product=latte,
        ingredient=milk,
        quantity=Decimal("2.0"),
        unit="oz",
    )

    StockEntry.objects.create(
        ingredient=milk,
        quantity_added=Decimal("100.0"),
        cost_per_unit=Decimal("1.00"),
        date_received=timezone.make_aware(datetime.datetime(2024, 1, 1, 8, 0)),
    )

    americano = Product.objects.create(name="Americano", sku="AMER-8")
    americano.categories.add(coffee_cat)
    RecipeItem.objects.create(
        product=americano,
        ingredient=milk,
        quantity=Decimal("1.0"),
        unit="oz",
    )

    order = Order.objects.create(
        order_id="100",
        platform="square",
        order_date=order_dt,
        total_amount=Decimal("0.00"),
    )

    OrderItem.objects.create(
        order=order,
        product=latte,
        quantity=3,
        unit_price=Decimal("5.00"),
        variant_info={
            "adjectives": ["iced", "large"],
            "modifiers": ["pumpkin spice", "oat milk", "regular"],
        },
    )

    OrderItem.objects.create(
        order=order,
        product=americano,
        quantity=2,
        unit_price=Decimal("4.00"),
        variant_info={
            "adjectives": ["hot"],
            "modifiers": ["extra shot"],
        },
    )

    IngredientUsageLog.objects.create(
        ingredient=milk,
        date=report_date,
        quantity_used=Decimal("8.0"),
        source="square",
    )
    IngredientUsageLog.objects.create(
        ingredient=syrup,
        date=report_date,
        quantity_used=Decimal("1.0"),
        source="square",
    )

    product_rows = reports.cogs_summary_by_product(report_date, report_date)
    assert product_rows[0]["product_name"] == "Latte"
    assert product_rows[0]["quantity"] == Decimal("3")
    assert product_rows[0]["revenue"] == Decimal("15.00")
    assert product_rows[0]["cogs"] == Decimal("6.00")

    category_rows = reports.cogs_summary_by_category(report_date, report_date)
    categories = {row["category"]: row for row in category_rows}
    assert categories["Coffee"]["quantity"] == Decimal("3.5")
    assert categories["Coffee"]["revenue"] == Decimal("15.5")
    assert categories["Coffee"]["cogs"] == Decimal("5")
    assert categories["Seasonal"]["quantity"] == Decimal("1.5")
    assert categories["Seasonal"]["revenue"] == Decimal("7.5")
    assert categories["Seasonal"]["cogs"] == Decimal("3")

    profitability = reports.category_profitability(report_date, report_date)
    assert profitability["overall_revenue"] == Decimal("23.00")
    assert profitability["overall_cogs"] == Decimal("8.00")

    trend = reports.cogs_trend_with_variance(report_date, report_date)
    assert trend[0]["cogs_total"] == Decimal("8.00")
    assert trend[0]["variance"] is None
    assert trend[0]["date_obj"] == report_date

    usage_totals = reports.aggregate_usage_totals(report_date, report_date)
    milk_row = next(row for row in usage_totals if row["ingredient"] == "Milk")
    assert milk_row["quantity"] == Decimal("8.0")
    assert milk_row["unit"] == "units"

    linkage = reports.validate_cogs_linkage(report_date, report_date)
    assert linkage["missing_cost_ingredients"] == ["Pumpkin Syrup"]

    top_products = reports.top_selling_products(report_date, report_date)
    assert top_products[0]["product_name"] == "Latte"
    assert top_products[0]["variant_count"] == 1
    assert tuple(top_products[0]["modifiers"]) == ("oat milk", "pumpkin spice")
    assert set(top_products[0]["suppressed_descriptors"]) == {"iced", "large"}
    latte_variant = top_products[0]["variant_details"][0]
    assert latte_variant["quantity"] == Decimal("3")
    assert latte_variant["gross_sales"] == Decimal("15.00")
    assert latte_variant["adjectives"] == tuple()
    assert set(latte_variant["suppressed_descriptors"]) == {"iced", "large"}


@pytest.mark.django_db
def test_top_products_modifier_order_reflects_usage_counts():
    report_date = datetime.date(2024, 6, 10)
    order_dt = timezone.make_aware(datetime.datetime(2024, 6, 10, 11, 0))

    cappuccino = Product.objects.create(name="Cappuccino", sku="CAP-1")

    order = Order.objects.create(
        order_id="200",
        platform="square",
        order_date=order_dt,
        total_amount=Decimal("0.00"),
    )

    OrderItem.objects.create(
        order=order,
        product=cappuccino,
        quantity=2,
        unit_price=Decimal("5.00"),
        variant_info={"modifiers": ["caramel", "vanilla"]},
    )
    OrderItem.objects.create(
        order=order,
        product=cappuccino,
        quantity=1,
        unit_price=Decimal("5.00"),
        variant_info={"modifiers": ["vanilla"]},
    )

    top_products = reports.top_selling_products(report_date, report_date)

    assert top_products[0]["product_name"] == "Cappuccino"
    assert top_products[0]["modifiers"] == ("vanilla", "caramel")


@pytest.mark.django_db
def test_usage_logs_record_order_dates():
    ingredient = IngredientFactory()
    date_a = datetime.date(2024, 2, 1)
    date_b = datetime.date(2024, 2, 3)

    usage_by_date = {
        date_a: {ingredient.id: Decimal("1.500")},
        date_b: {ingredient.id: Decimal("2.000")},
    }

    write_usage_logs(usage_by_date, source="square")

    logs = IngredientUsageLog.objects.order_by("date")
    assert [log.date for log in logs] == [date_a, date_b]
    assert logs[0].quantity_used == Decimal("1.500")
    assert logs[1].quantity_used == Decimal("2.000")


@pytest.mark.django_db
def test_cogs_trend_and_usage_totals_follow_order_dates():
    ingredient = IngredientFactory(average_cost_per_unit=Decimal("2.00"))
    StockEntry.objects.create(
        ingredient=ingredient,
        quantity_added=Decimal("10.0"),
        cost_per_unit=Decimal("2.00"),
        date_received=timezone.make_aware(datetime.datetime(2024, 1, 1, 8, 0)),
    )

    date_a = datetime.date(2024, 2, 1)
    date_b = datetime.date(2024, 2, 2)
    usage_by_date = {
        date_a: {ingredient.id: Decimal("1.000")},
        date_b: {ingredient.id: Decimal("3.000")},
    }
    write_usage_logs(usage_by_date, source="shopify")

    trend = reports.cogs_trend_with_variance(date_a, date_b)
    assert trend[0]["date_obj"] == date_a
    assert trend[0]["cogs_total"] == Decimal("2.00")
    assert trend[1]["date_obj"] == date_b
    assert trend[1]["cogs_total"] == Decimal("6.00")
    assert trend[1]["variance"] == Decimal("4.00")

    totals = reports.aggregate_usage_totals(date_a, date_b)
    total_row = next(row for row in totals if row["ingredient"] == ingredient.name)
    assert total_row["quantity"] == Decimal("4.000")
    assert total_row["unit"] == ingredient.unit_type.abbreviation


@pytest.mark.django_db
def test_top_rank_changes_include_previous_window():
    today = datetime.date(2024, 3, 3)
    prev_day = today - datetime.timedelta(days=1)

    product_a = Product.objects.create(name="Latte", sku="LAT-1")
    product_b = Product.objects.create(name="Mocha", sku="MOC-1")

    prev_order = Order.objects.create(
        order_id="prev",
        platform="square",
        order_date=timezone.make_aware(datetime.datetime.combine(prev_day, datetime.time(10, 0))),
        total_amount=Decimal("0"),
    )
    OrderItem.objects.create(
        order=prev_order,
        product=product_b,
        quantity=5,
        unit_price=Decimal("3.00"),
        variant_info={"modifiers": ["vanilla"]},
    )

    current_order = Order.objects.create(
        order_id="curr",
        platform="square",
        order_date=timezone.make_aware(datetime.datetime.combine(today, datetime.time(9, 0))),
        total_amount=Decimal("0"),
    )
    OrderItem.objects.create(
        order=current_order,
        product=product_a,
        quantity=5,
        unit_price=Decimal("6.00"),
        variant_info={"modifiers": ["vanilla", "mocha"]},
    )
    OrderItem.objects.create(
        order=current_order,
        product=product_b,
        quantity=2,
        unit_price=Decimal("4.00"),
        variant_info={"modifiers": ["vanilla"]},
    )

    products = reports.top_selling_products_with_changes(today, today)
    assert products[0]["product_name"] == "Latte"
    assert products[0]["previous_rank"] is None
    assert products[0]["rank_delta"] is None
    mocha_row = next(row for row in products if row["product_name"] == "Mocha")
    assert mocha_row["previous_rank"] == 1
    assert mocha_row["rank_delta"] == -1

    modifiers = reports.top_modifiers_with_changes(today, today)
    vanilla_row = next(row for row in modifiers if row["modifier"].lower() == "vanilla")
    assert vanilla_row["previous_rank"] == 1
    assert vanilla_row["rank_delta"] == 0
    mocha_mod = next(row for row in modifiers if row["modifier"].lower() == "mocha")
    assert mocha_mod["previous_rank"] is None
    assert mocha_mod["rank_delta"] is None


@pytest.mark.django_db
def test_usage_detail_by_day_includes_units():
    day = datetime.date(2024, 2, 10)
    ingredient = IngredientFactory(unit_type__name="Ounce", unit_type__abbreviation="oz")
    IngredientUsageLog.objects.create(
        ingredient=ingredient,
        date=day,
        quantity_used=Decimal("2.500"),
        source="manual",
    )

    rows = reports.usage_detail_by_day(day, day)
    assert rows[0]["unit"] == "oz"
    assert rows[0]["qty_used"] == Decimal("2.500")


@pytest.mark.django_db
def test_top_modifiers_include_unit_labels():
    today = datetime.date(2024, 5, 5)
    unit_type = UnitType.objects.create(name="Pump", abbreviation="pump")
    ingredient_type = IngredientType.objects.create(name="Syrup")
    vanilla = IngredientFactory(name="Vanilla Syrup", unit_type=unit_type, type=ingredient_type)
    RecipeModifier.objects.create(
        name="vanilla",
        ingredient_type=ingredient_type,
        ingredient=vanilla,
        base_quantity=Decimal("1.00"),
        unit="",
    )

    order = Order.objects.create(
        order_id="tm-1",
        platform="square",
        order_date=timezone.make_aware(datetime.datetime.combine(today, datetime.time(9, 0))),
        total_amount=Decimal("5.00"),
    )
    OrderItem.objects.create(
        order=order,
        product=Product.objects.create(name="Latte", sku="LAT-1"),
        quantity=1,
        unit_price=Decimal("5.00"),
        variant_info={"modifiers": ["Vanilla"]},
    )

    rows = reports.top_modifiers(today, today)
    assert rows[0]["modifier"] == vanilla.name
    assert rows[0]["unit"] == "pump"
