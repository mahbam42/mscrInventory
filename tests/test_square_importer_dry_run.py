from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command

from importers import square_importer
from importers.square_importer import SquareImporter
from mscrInventory.models import (
    Ingredient,
    IngredientUsageLog,
    Order,
    OrderItem,
    Product,
    ProductVariantCache,
    SquareUnmappedItem,
)


@pytest.mark.django_db
def test_square_importer_dry_run_skips_writes(tmp_path, monkeypatch):
    csv_path = tmp_path / "square.csv"
    csv_path.write_text(
        "Item,Qty,Gross Sales,Modifiers Applied,Price Point Name,Transaction ID\n"
        "Latte,1,5.00,,,txn-dry\n"
    )

    monkeypatch.setattr(
        square_importer,
        "_find_best_product_match",
        lambda *args, **kwargs: (None, "no match"),
    )

    importer = SquareImporter(dry_run=True)
    output = importer.run_from_file(csv_path)

    assert "Dry-run" in output
    assert "no product match found" in output.lower()
    assert Order.objects.count() == 0
    assert OrderItem.objects.count() == 0
    assert ProductVariantCache.objects.count() == 0
    assert importer.stats["unmatched"] == 1
    assert importer.stats["order_items_logged"] == 0
    summary = importer.get_summary()
    assert "Unmatched items: 1" in summary
    assert SquareUnmappedItem.objects.count() == 1
    unmapped = SquareUnmappedItem.objects.get()
    assert unmapped.item_name == "Latte"
    assert unmapped.seen_count == 1


@pytest.mark.django_db
def test_square_importer_skips_voided_items(tmp_path, monkeypatch):
    csv_path = tmp_path / "square_voided.csv"
    csv_path.write_text(
        "Item,Qty,Gross Sales,Modifiers Applied,Price Point Name,Transaction ID\n"
        "Latte (Voided),1,5.00,,,txn-void\n"
    )

    def should_not_run(*args, **kwargs):
        raise AssertionError("_find_best_product_match should not be called for voided items")

    monkeypatch.setattr(square_importer, "_find_best_product_match", should_not_run)

    importer = SquareImporter(dry_run=True)
    output = importer.run_from_file(csv_path)

    assert "voided" in output.lower()
    assert importer.stats["matched"] == 0
    assert importer.stats["unmatched"] == 0
    assert importer.stats["order_items_logged"] == 0
    assert SquareUnmappedItem.objects.count() == 0


@pytest.mark.django_db
def test_square_importer_live_creates_orders(tmp_path, monkeypatch):
    product = Product.objects.create(name="Latte", sku="LATTE-1")

    csv_path = tmp_path / "square_live.csv"
    csv_path.write_text(
        "Item,Qty,Gross Sales,Modifiers Applied,Price Point Name,Transaction ID\n"
        "Latte,2,10.00,,,txn-live\n"
    )

    monkeypatch.setattr(
        square_importer,
        "_find_best_product_match",
        lambda *args, **kwargs: (product, "exact name"),
    )
    monkeypatch.setattr(square_importer, "handle_extras", lambda *a, **k: ({}, {}))
    monkeypatch.setattr(square_importer, "resolve_modifier_tree", lambda *a, **k: [])
    monkeypatch.setattr(square_importer, "aggregate_ingredient_usage", lambda *a, **k: {})
    monkeypatch.setattr(square_importer, "infer_temp_and_size", lambda *a, **k: (None, None))

    importer = SquareImporter(dry_run=False)
    output = importer.run_from_file(csv_path)

    assert "Import complete" in output
    assert Order.objects.count() == 1
    assert OrderItem.objects.count() == 1
    assert ProductVariantCache.objects.count() == 0
    assert importer.stats["matched"] == 1
    assert importer.stats["order_items_logged"] == 1


@pytest.mark.django_db
def test_square_importer_tracks_usage_totals(tmp_path, monkeypatch):
    ingredient = Ingredient.objects.create(name="Latte Base")
    product = Product.objects.create(name="Latte", sku="LATTE-1")

    csv_path = tmp_path / "square_usage.csv"
    csv_path.write_text(
        "Item,Qty,Gross Sales,Modifiers Applied,Price Point Name,Transaction ID\n"
        "Latte,2,10.00,,,txn-usage\n"
    )

    monkeypatch.setattr(
        square_importer,
        "_find_best_product_match",
        lambda *args, **kwargs: (product, "exact name"),
    )
    monkeypatch.setattr(square_importer, "handle_extras", lambda *a, **k: ({}, {}))
    monkeypatch.setattr(square_importer, "resolve_modifier_tree", lambda *a, **k: [])

    def fake_aggregate(*args, **kwargs):
        return {"Latte Base": {"qty": Decimal("1"), "sources": ["base"]}}

    monkeypatch.setattr(square_importer, "aggregate_ingredient_usage", fake_aggregate)
    monkeypatch.setattr(square_importer, "infer_temp_and_size", lambda *a, **k: (None, None))

    importer = SquareImporter(dry_run=False)
    importer.run_from_file(csv_path)

    assert importer.usage_totals[ingredient.id] == Decimal("2")
    breakdown = importer.get_usage_breakdown()
    assert "Latte Base" in breakdown
    assert sum(breakdown["Latte Base"].values()) == Decimal("2")


@pytest.mark.django_db
def test_import_square_logs_usage(tmp_path, monkeypatch):
    ingredient = Ingredient.objects.create(name="Latte Base")
    product = Product.objects.create(name="Latte", sku="LATTE-1")

    csv_path = tmp_path / "square_cmd_live.csv"
    csv_path.write_text(
        "Item,Qty,Gross Sales,Modifiers Applied,Price Point Name,Transaction ID\n"
        "Latte,2,10.00,,,txn-cmd-live\n"
    )

    monkeypatch.setattr(
        square_importer,
        "_find_best_product_match",
        lambda *args, **kwargs: (product, "exact name"),
    )
    monkeypatch.setattr(square_importer, "handle_extras", lambda *a, **k: ({}, {}))
    monkeypatch.setattr(square_importer, "resolve_modifier_tree", lambda *a, **k: [])

    def fake_aggregate(*args, **kwargs):
        return {"Latte Base": {"qty": Decimal("1"), "sources": ["base"]}}

    monkeypatch.setattr(square_importer, "aggregate_ingredient_usage", fake_aggregate)
    monkeypatch.setattr(square_importer, "infer_temp_and_size", lambda *a, **k: (None, None))

    out = StringIO()
    call_command("import_square", file=str(csv_path), date="2024-01-02", stdout=out)

    log = IngredientUsageLog.objects.get()
    assert log.ingredient == ingredient
    assert log.date.isoformat() == "2024-01-02"
    assert log.quantity_used == Decimal("2.000")
    assert log.source == "square"
    assert log.calculated_from_orders is True


@pytest.mark.django_db
def test_import_square_command_respects_dry_run(tmp_path, monkeypatch):
    csv_path = tmp_path / "square_cmd.csv"
    csv_path.write_text(
        "Item,Qty,Gross Sales,Modifiers Applied,Price Point Name,Transaction ID\n"
        "Latte,1,5.00,,,txn-cmd\n"
    )

    monkeypatch.setattr(
        square_importer,
        "_find_best_product_match",
        lambda *args, **kwargs: (None, "no match"),
    )

    out = StringIO()
    call_command("import_square", file=str(csv_path), dry_run=True, stdout=out)

    output = out.getvalue()
    assert "dry-run" in output.lower()
    assert "✅ Done." in output
    assert Order.objects.count() == 0
    assert OrderItem.objects.count() == 0


@pytest.mark.django_db
def test_baristas_choice_variant_treated_as_unmapped(tmp_path):
    Product.objects.create(name="Barista's Choice", sku="BAR-001")

    csv_path = tmp_path / "barista.csv"
    csv_path.write_text(
        "Item,Qty,Gross Sales,Modifiers Applied,Price Point Name,Transaction ID\n"
        "Barista's Choice,1,7.50,,Dracula's Delight,txn-dracula\n"
    )

    importer = SquareImporter(dry_run=True)
    output = importer.run_from_file(csv_path)

    assert "Variant 'Dracula's Delight' not mapped" in output
    assert importer.stats["unmatched"] == 1
    assert importer.stats["matched"] == 0


@pytest.mark.django_db
def test_square_importer_live_rerun_is_idempotent(tmp_path, monkeypatch):
    product = Product.objects.create(name="Latte", sku="LATTE-1")

    csv_path = tmp_path / "square_live.csv"
    csv_path.write_text(
        "Item,Qty,Gross Sales,Modifiers Applied,Price Point Name,Transaction ID\n"
        "Latte,2,10.00,,,txn-live\n"
    )

    monkeypatch.setattr(
        square_importer,
        "_find_best_product_match",
        lambda *args, **kwargs: (product, "exact name"),
    )
    monkeypatch.setattr(square_importer, "handle_extras", lambda *a, **k: ({}, {}))
    monkeypatch.setattr(square_importer, "resolve_modifier_tree", lambda *a, **k: [])
    monkeypatch.setattr(square_importer, "aggregate_ingredient_usage", lambda *a, **k: {})
    monkeypatch.setattr(square_importer, "infer_temp_and_size", lambda *a, **k: (None, None))

    importer = SquareImporter(dry_run=False)
    importer.run_from_file(csv_path)

    importer_second = SquareImporter(dry_run=False)
    importer_second.run_from_file(csv_path)

    assert Order.objects.count() == 1
    order = Order.objects.get()
    assert order.items.count() == 1
    assert order.total_amount == Decimal("10.00")

    order_item = order.items.get()
    assert order_item.quantity == 2
    assert importer_second.stats["order_items_logged"] == 1


@pytest.mark.django_db
def test_unmapped_items_recorded_once_with_counts(tmp_path):
    csv_path = tmp_path / "unmapped.csv"
    csv_path.write_text(
        "Item,Qty,Gross Sales,Modifiers Applied,Price Point Name,Transaction ID\n"
        "Mystery Drink,1,5.00,Decaf.,,txn-mystery\n"
    )

    importer = SquareImporter(dry_run=False)
    importer.run_from_file(csv_path)

    assert SquareUnmappedItem.objects.count() == 1
    item = SquareUnmappedItem.objects.get()
    assert item.item_name == "Mystery Drink"
    assert item.seen_count == 1
    assert item.last_modifiers == ["decaf"]

    importer_second = SquareImporter(dry_run=False)
    importer_second.run_from_file(csv_path)

    assert SquareUnmappedItem.objects.count() == 1
    item.refresh_from_db()
    assert item.seen_count == 2


@pytest.mark.django_db
def test_resolved_unmapped_mapping_reused(tmp_path, monkeypatch):
    csv_path = tmp_path / "unmapped.csv"
    csv_path.write_text(
        "Item,Qty,Gross Sales,Modifiers Applied,Price Point Name,Transaction ID\n"
        "Mystery Drink,1,5.00,,Medium,txn-1\n"
    )

    monkeypatch.setattr(
        square_importer,
        "_find_best_product_match",
        lambda *args, **kwargs: (None, "no match"),
    )

    importer = SquareImporter(dry_run=True)
    importer.run_from_file(csv_path)

    item = SquareUnmappedItem.objects.get()
    product = Product.objects.create(name="Mystery Drink", sku="MYS-001")
    item.mark_resolved(product=product)

    def should_not_run(*args, **kwargs):
        raise AssertionError("Matching should reuse saved mapping")

    monkeypatch.setattr(square_importer, "_find_best_product_match", should_not_run)
    monkeypatch.setattr(square_importer, "handle_extras", lambda *a, **k: ({}, {}))
    monkeypatch.setattr(square_importer, "resolve_modifier_tree", lambda *a, **k: [])
    monkeypatch.setattr(square_importer, "aggregate_ingredient_usage", lambda *a, **k: {})
    monkeypatch.setattr(square_importer, "infer_temp_and_size", lambda *a, **k: (None, None))

    importer_live = SquareImporter(dry_run=False)
    importer_live.run_from_file(csv_path)

    item.refresh_from_db()

    assert importer_live.stats["matched"] == 1
    assert importer_live.stats["unmatched"] == 0
    assert item.resolved is True
    assert item.ignored is False
    assert item.linked_product == product
    assert item.seen_count == 1
    assert SquareUnmappedItem.objects.count() == 1


@pytest.mark.django_db
def test_square_importer_live_creates_orders_per_transaction(tmp_path, monkeypatch):
    product = Product.objects.create(name="Latte", sku="LATTE-1")

    csv_path = tmp_path / "square_multi.csv"
    csv_path.write_text(
        "Item,Qty,Gross Sales,Modifiers Applied,Price Point Name,Transaction ID\n"
        "Latte,1,5.00,,,txn-a\n"
        "Latte,1,5.00,,,txn-b\n"
    )

    monkeypatch.setattr(
        square_importer,
        "_find_best_product_match",
        lambda *args, **kwargs: (product, "exact name"),
    )
    monkeypatch.setattr(square_importer, "handle_extras", lambda *a, **k: ({}, {}))
    monkeypatch.setattr(square_importer, "resolve_modifier_tree", lambda *a, **k: [])
    monkeypatch.setattr(square_importer, "aggregate_ingredient_usage", lambda *a, **k: {})
    monkeypatch.setattr(square_importer, "infer_temp_and_size", lambda *a, **k: (None, None))

    importer = SquareImporter(dry_run=False)
    importer.run_from_file(csv_path)

    orders = Order.objects.order_by("order_id")
    assert orders.count() == 2
    assert {order.order_id for order in orders} == {"txn-a", "txn-b"}
    for order in orders:
        assert order.items.count() == 1
        assert order.total_amount == Decimal("5.00")


@pytest.mark.django_db
def test_price_point_size_tokens_feed_handle_extras(tmp_path, monkeypatch):
    product = Product.objects.create(name="Catering To Go Box", sku="CAT-BOX")
    csv_path = tmp_path / "catering.csv"
    csv_path.write_text(
        "Item,Qty,Gross Sales,Modifiers Applied,Price Point Name,Transaction ID\n"
        "\"Catering Hot and Cold Box 96oz -\",1,31.00,,\"Cold Brew Coffee- Medium\",txn-cold-hot\n"
    )

    monkeypatch.setattr(
        square_importer,
        "_find_best_product_match",
        lambda *args, **kwargs: (product, "exact"),
    )
    monkeypatch.setattr(square_importer, "resolve_modifier_tree", lambda *a, **k: [])
    monkeypatch.setattr(square_importer, "aggregate_ingredient_usage", lambda *a, **k: {})

    captured_tokens = []

    def fake_handle_extras(modifier_name, recipe_map, normalized_modifiers, **kwargs):
        captured_tokens.append(modifier_name)
        return recipe_map, {"added": [], "replaced": [], "behavior": None}

    monkeypatch.setattr(square_importer, "handle_extras", fake_handle_extras)

    importer = SquareImporter(dry_run=True)
    importer.run_from_file(csv_path)

    assert "medium" in captured_tokens
    assert "hot" not in captured_tokens
