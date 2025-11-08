from datetime import datetime
from pathlib import Path

import pytest

from django.utils import timezone

from importers import square_importer
from importers.square_importer import SquareImporter
from mscrInventory.models import Order, Product


@pytest.mark.django_db
def test_square_importer_sets_order_date_from_csv(monkeypatch):
    product = Product.objects.create(name="Latte", sku="LATTE-1")
    monkeypatch.setattr(
        square_importer,
        "_find_best_product_match",
        lambda *args, **kwargs: (product, "exact"),
    )
    monkeypatch.setattr(square_importer, "handle_extras", lambda *a, **k: ({}, {}))
    monkeypatch.setattr(square_importer, "resolve_modifier_tree", lambda *a, **k: [])
    monkeypatch.setattr(square_importer, "aggregate_ingredient_usage", lambda *a, **k: {})
    monkeypatch.setattr(square_importer, "infer_temp_and_size", lambda *a, **k: (None, None))

    importer = SquareImporter(dry_run=False)
    row = {
        "Item": "Latte",
        "Price Point Name": "",
        "Modifiers Applied": "",
        "Qty": "1",
        "Gross Sales": "5.00",
        "Date": "03/15/2024",
        "Time": "1:23 PM",
        "Transaction ID": "txn-100",
    }

    with timezone.override("UTC"):
        importer._process_row(row, file_path=Path("square.csv"))
        expected = timezone.make_aware(
            datetime(2024, 3, 15, 13, 23),
            timezone=timezone.get_current_timezone(),
        )

    order = Order.objects.get(order_id="txn-100", platform="square")
    assert order.order_date == expected


@pytest.mark.django_db
def test_square_importer_preserves_earliest_order_datetime(monkeypatch):
    product = Product.objects.create(name="Latte", sku="LATTE-2")
    monkeypatch.setattr(
        square_importer,
        "_find_best_product_match",
        lambda *args, **kwargs: (product, "exact"),
    )
    monkeypatch.setattr(square_importer, "handle_extras", lambda *a, **k: ({}, {}))
    monkeypatch.setattr(square_importer, "resolve_modifier_tree", lambda *a, **k: [])
    monkeypatch.setattr(square_importer, "aggregate_ingredient_usage", lambda *a, **k: {})
    monkeypatch.setattr(square_importer, "infer_temp_and_size", lambda *a, **k: (None, None))

    importer = SquareImporter(dry_run=False)
    file_path = Path("square.csv")
    early_row = {
        "Item": "Latte",
        "Price Point Name": "",
        "Modifiers Applied": "",
        "Qty": "1",
        "Gross Sales": "5.00",
        "Date": "03/15/2024",
        "Time": "8:15 AM",
        "Transaction ID": "txn-200",
    }
    later_row = {
        "Item": "Latte",
        "Price Point Name": "",
        "Modifiers Applied": "",
        "Qty": "1",
        "Gross Sales": "4.00",
        "Date": "03/15/2024",
        "Time": "10:30 AM",
        "Transaction ID": "txn-200",
    }

    with timezone.override("UTC"):
        importer._process_row(early_row, file_path=file_path)
        importer._process_row(later_row, file_path=file_path)
        expected = timezone.make_aware(
            datetime(2024, 3, 15, 8, 15),
            timezone=timezone.get_current_timezone(),
        )

    order = Order.objects.get(order_id="txn-200", platform="square")
    assert order.order_date == expected


@pytest.mark.django_db
def test_square_importer_updates_to_earlier_datetime_when_needed(monkeypatch):
    product = Product.objects.create(name="Latte", sku="LATTE-3")
    monkeypatch.setattr(
        square_importer,
        "_find_best_product_match",
        lambda *args, **kwargs: (product, "exact"),
    )
    monkeypatch.setattr(square_importer, "handle_extras", lambda *a, **k: ({}, {}))
    monkeypatch.setattr(square_importer, "resolve_modifier_tree", lambda *a, **k: [])
    monkeypatch.setattr(square_importer, "aggregate_ingredient_usage", lambda *a, **k: {})
    monkeypatch.setattr(square_importer, "infer_temp_and_size", lambda *a, **k: (None, None))

    importer = SquareImporter(dry_run=False)
    file_path = Path("square.csv")
    initial_row = {
        "Item": "Latte",
        "Price Point Name": "",
        "Modifiers Applied": "",
        "Qty": "1",
        "Gross Sales": "5.00",
        "Date": "03/15/2024",
        "Time": "9:45 AM",
        "Transaction ID": "txn-300",
    }
    earlier_row = {
        "Item": "Latte",
        "Price Point Name": "",
        "Modifiers Applied": "",
        "Qty": "1",
        "Gross Sales": "3.50",
        "Date": "03/15/2024",
        "Time": "9:15 AM",
        "Transaction ID": "txn-300",
    }

    with timezone.override("UTC"):
        importer._process_row(initial_row, file_path=file_path)
        importer._process_row(earlier_row, file_path=file_path)
        expected = timezone.make_aware(
            datetime(2024, 3, 15, 9, 15),
            timezone=timezone.get_current_timezone(),
        )

    order = Order.objects.get(order_id="txn-300", platform="square")
    assert order.order_date == expected
