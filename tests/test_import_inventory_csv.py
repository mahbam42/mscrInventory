import io, csv, pytest
from decimal import Decimal
from django.urls import reverse
from mscrInventory.models import Ingredient

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
