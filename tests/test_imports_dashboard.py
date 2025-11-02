import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from importers import square_importer
from mscrInventory.models import ImportLog, Ingredient, SquareUnmappedItem


@pytest.mark.django_db
def test_upload_square_view_logs_output(client, monkeypatch):
    csv_content = "Item,Qty\nLatte,1\n"
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
    log = ImportLog.objects.get(source="square")
    assert "Test output" in log.log_excerpt


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
    assert "Barista&#x27;s Choice" in content
    assert "Dracula&#x27;s Delight" in content
    assert "Unmapped: Syrup" in content


@pytest.mark.django_db
def test_unmapped_items_view_page(client):
    SquareUnmappedItem.objects.create(item_name="Seasonal Special", price_point_name="")
    response = client.get(reverse("imports_unmapped_items"))
    assert response.status_code == 200
    assert b"Unmapped Square Items" in response.content
    assert b"Seasonal Special" in response.content
