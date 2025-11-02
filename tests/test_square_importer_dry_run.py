from io import StringIO
from decimal import Decimal

import pytest
from django.core.management import call_command

from importers import square_importer
from importers.square_importer import SquareImporter
from mscrInventory.models import (
    Order,
    OrderItem,
    Product,
    ProductVariantCache,
    SquareUnmappedItem,
)


@pytest.mark.django_db
def test_square_importer_dry_run_skips_writes(tmp_path, monkeypatch):
    csv_path = tmp_path / "square.csv"
    csv_path.write_text("Item,Qty,Gross Sales,Modifiers Applied,Price Point Name\nLatte,1,5.00,,\n")

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


@pytest.mark.django_db
def test_square_importer_live_creates_orders(tmp_path, monkeypatch):
    product = Product.objects.create(name="Latte", sku="LATTE-1")

    csv_path = tmp_path / "square_live.csv"
    csv_path.write_text("Item,Qty,Gross Sales,Modifiers Applied,Price Point Name\nLatte,2,10.00,,\n")

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
def test_import_square_command_respects_dry_run(tmp_path, monkeypatch):
    csv_path = tmp_path / "square_cmd.csv"
    csv_path.write_text("Item,Qty,Gross Sales,Modifiers Applied,Price Point Name\nLatte,1,5.00,,\n")

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
        "Item,Qty,Gross Sales,Modifiers Applied,Price Point Name\n"
        "Barista's Choice,1,7.50,,Dracula's Delight\n"
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
    csv_path.write_text("Item,Qty,Gross Sales,Modifiers Applied,Price Point Name\nLatte,2,10.00,,\n")

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
        "Item,Qty,Gross Sales,Modifiers Applied,Price Point Name\n"
        "Mystery Drink,1,5.00,Decaf.,\n"
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
