import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

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
)
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
    assert usage_totals["Milk"] == Decimal("8.0")

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

    top_mods = reports.top_modifiers(report_date, report_date)
    modifier_names = {row["modifier"] for row in top_mods}
    assert modifier_names == {"Pumpkin Spice Syrup", "Oat Milk", "Dark Cold Brew"}
    extra_shot = next(row for row in top_mods if row["modifier"] == "Dark Cold Brew")
    assert extra_shot["quantity"] == Decimal("2")
    assert extra_shot["unit"] == "shot"
    assert extra_shot["original_label"] == "extra shot"
