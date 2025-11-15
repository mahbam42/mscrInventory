import csv
import io
import json

import pytest
from decimal import Decimal
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from mscrInventory.models import Ingredient
from mscrInventory.views.inventory import REQUIRED_HEADERS
from tests.factories import IngredientFactory

@pytest.mark.django_db
def test_import_inventory_csv_updates_existing(client):
    i = Ingredient.objects.create(name="Whole Milk", current_stock=5)
    data = io.StringIO()
    writer = csv.writer(data)
    writer.writerow(["id", "name", "type", "current_stock", "case_size", "reorder_point", "average_cost_per_unit", "lead_time"])
    writer.writerow([i.id, i.name, "", 42, "", "", "", ""])
    data.seek(0)
    resp = client.post(
        reverse("import_inventory_csv"),
        {"file": io.BytesIO(data.getvalue().encode("utf-8"))},
        format="multipart",
    )
    assert resp.status_code in (200, 302)
    i.refresh_from_db()
    assert i.current_stock == Decimal("5.000")  # unchanged after import


@pytest.mark.django_db
def test_import_inventory_preview_includes_current_stock_value(client):
    ingredient = IngredientFactory()
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(REQUIRED_HEADERS)
    writer.writerow(
        [
            ingredient.id,
            ingredient.name,
            ingredient.type.name,
            "7.25",
            "12.50",
            "24",
            "6",
            "1.85",
            "3",
        ]
    )
    csv_buffer.seek(0)
    upload = SimpleUploadedFile(
        "inventory.csv",
        csv_buffer.getvalue().encode("utf-8"),
        content_type="text/csv",
    )

    resp = client.post(reverse("import_inventory_csv"), {"file": upload})

    assert resp.status_code == 200
    assert resp.context["valid_rows"][0]["current_stock"] == "12.50"
    assert "12.50" in resp.content.decode()


@pytest.mark.django_db
def test_confirm_inventory_import_emits_hx_triggers(client):
    ingredient = IngredientFactory()
    ingredient.current_stock = Decimal("0")
    ingredient.save(update_fields=["current_stock"])
    ingredient.refresh_from_db()
    assert ingredient.current_stock == Decimal("0")
    payload = [
        {
            "ingredient": ingredient.id,
            "quantity_added": "5",
            "cost_per_unit": "1.25",
            "case_size": "10",
            "lead_time": "4",
            "reorder_point": "2",
        }
    ]

    resp = client.post(
        reverse("confirm_inventory_import"),
        data=json.dumps(payload),
        content_type="application/json",
    )

    assert resp.status_code == 200
    hx_header = resp.headers.get("HX-Trigger")
    assert hx_header
    events = json.loads(hx_header)
    assert events["inventory:refresh"] is True
    assert "showMessage" in events
    assert "stock entries" in events["showMessage"].get("text", "")

    ingredient.refresh_from_db()
    assert ingredient.current_stock > Decimal("0")
