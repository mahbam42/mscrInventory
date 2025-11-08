import datetime
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from importers import square_importer
from mscrInventory.forms import CreateFromUnmappedItemForm, LinkUnmappedItemForm
from mscrInventory.models import (
    ImportLog,
    Ingredient,
    IngredientUsageLog,
    Product,
    SquareUnmappedItem,
)


@pytest.mark.django_db
def test_upload_square_view_logs_output(client, monkeypatch):
    csv_content = "Item,Qty,Transaction ID\nLatte,1,txn-test\n"
    upload = SimpleUploadedFile("square.csv", csv_content.encode("utf-8"))

    def fake_run(self, path):
        self.buffer = ["Test output", "📊 **Square Import Summary**", "✅ Dry-run complete."]
        return "\n".join(self.buffer)

    monkeypatch.setattr(square_importer.SquareImporter, "run_from_file", fake_run, raising=False)

    response = client.post(
        reverse("upload_square"),
        {"square_csv": upload, "dry_run": "on"},
        format="multipart",
    )

    assert response.status_code == 302
    logs = ImportLog.objects.filter(source="square")
    assert logs.count() == 1
    log = logs.first()
    assert log.run_type == "dry-run"
    assert log.filename == "square.csv"
    assert "Test output" in (log.log_output or "")


@pytest.mark.django_db
def test_upload_square_view_uses_secure_tempfile(client, monkeypatch):
    captured_path: dict[str, Path] = {}

    def fake_run(self, path):
        captured_path["value"] = Path(path)
        return ""

    monkeypatch.setattr(square_importer.SquareImporter, "run_from_file", fake_run, raising=False)

    upload = SimpleUploadedFile("../../evil.csv", b"Item,Qty\nLatte,1\n")
    response = client.post(reverse("upload_square"), {"square_csv": upload}, format="multipart")

    assert response.status_code == 302
    secure_path = captured_path["value"]
    assert secure_path.parent == Path(tempfile.gettempdir())
    assert secure_path.name != "../../evil.csv"
    assert ".." not in secure_path.name
    assert not secure_path.exists()


@pytest.mark.django_db
def test_upload_square_view_records_usage_logs(client, monkeypatch):
    ingredient = Ingredient.objects.create(name="Cold Brew", average_cost_per_unit=Decimal("0.50"), current_stock=Decimal("10"))
    upload = SimpleUploadedFile("square.csv", b"Item,Qty\nCold Brew,2\n")

    usage_totals = {ingredient.id: Decimal("2.5")}
    usage_breakdown = {ingredient.name: {"square": Decimal("2.5")}}
    started_at = timezone.now()
    finished_at = started_at + datetime.timedelta(seconds=5)

    def fake_run(self, path):
        self.dry_run = getattr(self, "dry_run", False)
        return ""

    monkeypatch.setattr(square_importer.SquareImporter, "run_from_file", fake_run, raising=False)
    monkeypatch.setattr(square_importer.SquareImporter, "get_output", lambda self: "", raising=False)
    monkeypatch.setattr(square_importer.SquareImporter, "get_summary", lambda self: "Summary", raising=False)
    monkeypatch.setattr(
        square_importer.SquareImporter,
        "get_run_metadata",
        lambda self: {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": 5,
            "stats": {
                "rows_processed": 1,
                "matched": 1,
                "unmatched": 0,
                "order_items_logged": 1,
                "modifiers_applied": 0,
                "errors": 0,
            },
        },
        raising=False,
    )
    monkeypatch.setattr(square_importer.SquareImporter, "get_usage_totals", lambda self: usage_totals, raising=False)
    monkeypatch.setattr(square_importer.SquareImporter, "get_usage_breakdown", lambda self: usage_breakdown, raising=False)

    response = client.post(reverse("upload_square"), {"square_csv": upload}, format="multipart")

    assert response.status_code == 302
    logs = IngredientUsageLog.objects.filter(ingredient=ingredient, source="square")
    assert logs.count() == 1
    log = logs.first()
    assert log.quantity_used == Decimal("2.500")
    assert log.date == timezone.localdate()


@pytest.mark.django_db
def test_unmapped_items_view_modal(client):
    SquareUnmappedItem.objects.create(item_name="Barista's Choice", price_point_name="Dracula's Delight")
    Ingredient.objects.create(name="Unmapped: Syrup")

    response = client.get(
        reverse("imports_unmapped_items"),
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "modal-header" in content
    assert "Raw Name" in content
    assert "Link to Existing" in content
    assert "Barista&#x27;s Choice" in content
    assert "Dracula&#x27;s Delight" in content
    assert "Legacy Unmapped Ingredients" in content


@pytest.mark.django_db
def test_unmapped_items_view_page(client):
    SquareUnmappedItem.objects.create(item_name="Seasonal Special", price_point_name="")
    response = client.get(reverse("imports_unmapped_items"))
    assert response.status_code == 200
    assert b"Unmapped Square Items" in response.content
    assert b"Resolve All" in response.content
    assert b"Seasonal Special" in response.content


@pytest.mark.django_db
def test_unmapped_items_hide_known_recipes_by_default(client):
    Product.objects.create(name="Maple Latte", sku="MAPLE-001")
    SquareUnmappedItem.objects.create(item_name="Maple Latte", price_point_name="")
    SquareUnmappedItem.objects.create(item_name="Mystery Blend", price_point_name="")

    response = client.get(reverse("imports_unmapped_items"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Mystery Blend" in content
    assert '<div class="fw-semibold">Maple Latte' not in content
    assert "Show known recipes" in content
    assert "Hiding 1 known recipe" in content


@pytest.mark.django_db
def test_unmapped_items_toggle_reveals_known_recipes(client):
    product = Product.objects.create(name="Caramel Cold Brew", sku="CCB-123")
    SquareUnmappedItem.objects.create(item_name="Caramel Cold Brew", price_point_name="")

    response = client.get(reverse("imports_unmapped_items"), {"include_known": "true"})

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Caramel Cold Brew" in content
    assert "Known recipe" in content
    assert "Showing 1 known recipe" in content
    assert product.name in content


@pytest.mark.django_db
def test_known_recipe_forms_target_products():
    product = Product.objects.create(name="Coconut Cream Pie", sku="CCP-001")
    item = SquareUnmappedItem.objects.create(item_name="Coconut Cream Pie", item_type="ingredient")
    item.is_known_recipe = True

    link_form = LinkUnmappedItemForm(item=item)
    assert link_form.fields["target"].label == "Product"
    assert list(link_form.fields["target"].queryset) == [product]

    create_form = CreateFromUnmappedItemForm(item=item)
    assert "sku" in create_form.fields
    assert create_form.fields["sku"].label == "SKU"


@pytest.mark.django_db
def test_bulk_unmapped_create_products(client, django_user_model):
    user = django_user_model.objects.create_user(username="staff", password="pw", is_staff=True)
    client.force_login(user)

    SquareUnmappedItem.objects.create(item_name="Mystery Drink", price_point_name="Nightcap")
    response = client.post(
        reverse("imports_unmapped_bulk"),
        {"action": "create", "filter_type": "product"},
        follow=True,
    )

    assert response.status_code == 200
    assert Product.objects.filter(name="Nightcap").exists()
    assert SquareUnmappedItem.objects.filter(resolved=False, ignored=False).count() == 0


@pytest.mark.django_db
def test_import_logs_view_lists_entries(client, django_user_model):
    user = django_user_model.objects.create_user(username="viewer", password="pw")
    ImportLog.objects.create(
        source="square",
        run_type="dry-run",
        filename="example.csv",
        summary="Sample summary",
        log_output="Line one",
        uploaded_by=user,
    )

    response = client.get(reverse("import_logs"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "example.csv" in content
    assert "Sample summary" in content
