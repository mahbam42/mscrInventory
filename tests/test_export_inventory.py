import csv
from io import StringIO
import pytest
from django.urls import reverse
from mscrInventory.models import Ingredient, IngredientType

@pytest.mark.django_db
def test_export_inventory_csv_empty(client):
    url = reverse("export_inventory_csv")
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp["Content-Type"] == "text/csv"
    data = resp.content.decode("utf-8")
    rows = list(csv.reader(StringIO(data)))
    assert rows[0] == [
        "id","name","type","current_stock","case_size",
        "reorder_point","average_cost_per_unit","lead_time"
    ]
    # no data rows
    assert len(rows) == 1

@pytest.mark.django_db
def test_export_inventory_csv_with_rows(client):
    milk_type = IngredientType.objects.create(name="Milk")
    Ingredient.objects.create(
        name="Whole Milk", type=milk_type,
        current_stock=12, case_size=6, reorder_point=4,
        average_cost_per_unit=0.35, lead_time=2
    )
    Ingredient.objects.create(
        name="Vanilla Syrup", type=None,
        current_stock=20, case_size=12, reorder_point=6,
        average_cost_per_unit=0.12, lead_time=0
    )
    url = reverse("export_inventory_csv")
    resp = client.get(url)
    data = resp.content.decode("utf-8")
    rows = list(csv.reader(StringIO(data)))
    # header + 2 rows
    assert len(rows) == 3
    assert rows[0] == [
        "id","name","type","current_stock","case_size",
        "reorder_point","average_cost_per_unit","lead_time"
    ]
    # ensure deterministic order by name: Vanilla Syrup last
    names = [r[1] for r in rows[1:]]
    assert names == ["Vanilla Syrup", "Whole Milk"] or names == ["Whole Milk", "Vanilla Syrup"]
