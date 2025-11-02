import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from importers import square_importer
from mscrInventory.models import ImportLog, Ingredient, Product, SquareUnmappedItem


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
