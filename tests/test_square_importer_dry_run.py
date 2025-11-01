from io import StringIO

import pytest
from django.core.management import call_command

from importers import square_importer
from importers.square_importer import SquareImporter
from mscrInventory.models import Order, OrderItem, Product, ProductVariantCache


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
    assert Order.objects.count() == 0
    assert OrderItem.objects.count() == 0
    assert ProductVariantCache.objects.count() == 0


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
