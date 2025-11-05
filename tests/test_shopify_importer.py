from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone

from importers.shopify_importer import ShopifyImporter
from tests.factories import IngredientFactory, ProductFactory


@pytest.mark.django_db
def test_resolve_bag_weight_ounces_uses_aliases():
    importer = ShopifyImporter(dry_run=True)

    assert importer._resolve_bag_weight_ounces("5 lb") == Decimal("80")
    assert importer._resolve_bag_weight_ounces("80 oz") == Decimal("80")
    assert importer._resolve_bag_weight_ounces("3oz") == Decimal("3")
    assert importer._resolve_bag_weight_ounces("64oz") == Decimal("64")
    assert importer._resolve_bag_weight_ounces("mystery") == Decimal("1")


@pytest.mark.django_db
def test_track_usage_from_retail_bag_multiplies_by_weight():
    importer = ShopifyImporter(dry_run=True)
    roast = IngredientFactory(name="Morning Roast")
    product = ProductFactory(name="Retail Bag", sku="RB-001")

    importer._track_usage_from_item(
        {
            "product": product,
            "title": "5 lb Bulk Coffee",
            "quantity": Decimal("2"),
            "variant_info": {
                "variant_title": "5 lb / Whole Bean",
                "retail_bag": {
                    "is_retail_bag": True,
                    "bag_size": "5lb",
                    "roast_ingredient_id": roast.id,
                },
            },
        }
    )

    assert importer.usage_totals[roast.id] == Decimal("160")
    breakdown = importer.usage_breakdown[roast.id]
    assert breakdown["5 lb Bulk Coffee (5 lb / Whole Bean)"] == Decimal("160")


@pytest.mark.django_db
def test_import_shopify_csv_groups_rows_into_orders(tmp_path, monkeypatch):
    csv_path = tmp_path / "shopify.csv"
    csv_path.write_text(
        "order_id,created_at,sku,title,variant_title,quantity,price\n"
        "1001,2025-09-18T09:30:00-04:00,SINGLE,Single Origin,,2,5.50\n"
        "1001,,BLEND,House Blend,12 oz,1,4.00\n"
    )

    captured = {}

    def fake_import_window(self, start, end, *, orders):
        captured["start"] = start
        captured["end"] = end
        captured["orders"] = orders

    monkeypatch.setattr(ShopifyImporter, "import_window", fake_import_window)
    monkeypatch.setattr(ShopifyImporter, "summarize", lambda self: None)

    call_command(
        "import_shopify_csv",
        str(csv_path),
        date="2025-09-18",
        dry_run=True,
        verbosity=0,
    )

    assert "orders" in captured
    orders = captured["orders"]
    assert len(orders) == 1
    order = orders[0]
    assert order["id"] == "1001"
    assert Decimal(order["total_price"]) == Decimal("15.00")
    assert len(order["line_items"]) == 2
    assert order["line_items"][0]["quantity"] == 2
    assert order["line_items"][1]["quantity"] == 1

    start = captured["start"]
    end = captured["end"]
    assert start.tzinfo is not None
    assert end.tzinfo is not None
    assert start <= end
    assert timezone.is_aware(start) and timezone.is_aware(end)