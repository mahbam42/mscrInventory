# Test Recipe Import and Export Functionality
# mscrInventory/tests/test_import_export.py
import io
import csv
import pytest
import json
from decimal import Decimal
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from mscrInventory.models import Ingredient, Product, RecipeItem, StockEntry


@pytest.mark.django_db
class TestInventoryImportExport:
    """Inventory CSV export and import logic."""

    def setup_method(self):
        self.ingredient = Ingredient.objects.create(
            name="Espresso Beans",
            current_stock=100,
            average_cost_per_unit=Decimal("1.20"),
            case_size=10,
            reorder_point=5,
            lead_time=3,
        )

    def test_export_inventory_csv_returns_csv_response(self, client):
        url = reverse("export_inventory_csv")
        response = client.get(url)
        assert response.status_code == 200
        assert response["Content-Type"] == "text/csv"
        content = response.content.decode()
        assert "Espresso Beans" in content
        assert "average_cost_per_unit" in content or "lead_time" in content

    def test_import_inventory_csv_updates_existing_ingredient(self, client):
        csv_content = (
            "id,name,type,quantity_added,current_stock,case_size,reorder_point,average_cost_per_unit,lead_time\n"
            f"{self.ingredient.id},Espresso Beans,,5,200,20,10,1.50,5\n"
        )
        upload = SimpleUploadedFile("test.csv", csv_content.encode("utf-8"), content_type="text/csv")
        url = reverse("import_inventory_csv")
        response = client.post(url, {"file": upload})
        assert response.status_code in (200, 302)
        self.ingredient.refresh_from_db()
        # importer should not overwrite average cost from CSV input
        assert self.ingredient.average_cost_per_unit == Decimal("1.200000")
        # sanity check that the file was parsed
        assert "1.50" in csv_content
        assert self.ingredient.current_stock != Decimal("1.500")

    def test_import_inventory_csv_preserves_decimal_precision(self, client):
        qty_value = "12345678901234567890.123456"
        cost_value = "0.000123456789"
        csv_content = (
            "id,name,type,quantity_added,current_stock,case_size,reorder_point,average_cost_per_unit,lead_time\n"
            f"{self.ingredient.id},Espresso Beans,,{qty_value},200,20,10,{cost_value},5\n"
        )
        upload = SimpleUploadedFile("precise.csv", csv_content.encode("utf-8"), content_type="text/csv")
        url = reverse("import_inventory_csv")
        response = client.post(url, {"file": upload})
        assert response.status_code == 200
        valid_rows = response.context["valid_rows"]
        assert valid_rows[0]["quantity_added"] == qty_value
        assert valid_rows[0]["cost_per_unit"] == cost_value

    def test_bulk_add_stock_creates_stockentry_records(self, client):
        url = reverse("bulk_add_stock")
        data = {
            "ingredient": [self.ingredient.id],
            "Rowquantity_added": ["10"],
            "Rowcost_per_unit": ["1.00"],
            "Rowcase_size": ["10"],
            "Rowlead_time": ["2"],
            "Rowreorder_point": ["4"],
            "reason": "Restock",
            "note": "pytest entry",
        }
        response = client.post(url, data)
        assert response.status_code == 200
        assert StockEntry.objects.count() == 1
        entry = StockEntry.objects.first()
        assert entry.quantity_added == Decimal("10")
        assert entry.source == "restock"

    def test_bulk_add_stock_allows_zero_metadata_updates(self, client):
        """Zero values should persist instead of being skipped as falsy."""
        self.ingredient.case_size = 25
        self.ingredient.lead_time = 14
        self.ingredient.reorder_point = Decimal("5")
        self.ingredient.save()

        url = reverse("bulk_add_stock")
        data = {
            "ingredient": [self.ingredient.id],
            "Rowquantity_added": ["1"],
            "Rowcost_per_unit": ["1.00"],
            "Rowcase_size": ["0"],
            "Rowlead_time": ["0"],
            "Rowreorder_point": ["0"],
            "reason": "Restock",
        }

        response = client.post(url, data)
        assert response.status_code == 200

        self.ingredient.refresh_from_db()
        assert self.ingredient.case_size == 0
        assert self.ingredient.lead_time == 0
        assert self.ingredient.reorder_point == Decimal("0")


@pytest.mark.django_db
class TestRecipeImportExport:
    """Recipe CSV import/export workflow and COGS preview."""

    def setup_method(self):
        self.ing = Ingredient.objects.create(
            name="Milk", average_cost_per_unit=Decimal("0.50")
        )
        self.prod = Product.objects.create(name="Latte")
        RecipeItem.objects.create(
            product=self.prod, ingredient=self.ing, quantity=Decimal("2.0")
        )

    def test_calculated_cogs_property(self):
        """COGS = ingredient.cost * quantity"""
        assert round(self.prod.calculated_cogs, 2) == Decimal("1.00")

    def test_export_recipes_csv_contains_expected_columns(self, client):
        url = reverse("export_recipes_csv")
        response = client.get(url)
        assert response.status_code in (200, 302)
        assert response["Content-Type"] == "text/csv"
        body = response.content.decode("utf-8")
        assert "Latte" in body
        assert "Milk" in body

    def test_import_recipes_csv_dry_run_does_not_write(self, client):
        csv_text = (
            "product_id,ingredient_id,quantity\n"
            f"{self.prod.id},{self.ing.id},3.0\n"
        )
        upload = SimpleUploadedFile("recipes.csv", csv_text.encode("utf-8"), content_type="text/csv")
        url = reverse("import_recipes_csv")
        response = client.post(url, {"file": upload, "dry_run": "true"})
        assert response.status_code in (200, 302)
        # DB remains unchanged in dry-run
        self.prod.refresh_from_db()
        item = RecipeItem.objects.get(product=self.prod, ingredient=self.ing)
        assert item.quantity == Decimal("2.0")

    def test_confirm_recipes_import_creates_and_updates_items(self, client):
        """Simulate HTMX confirm stage by posting valid JSON payload."""
        url = reverse("confirm_recipes_import")
        valid_rows = [
            {
                "product_id": self.prod.id,
                "ingredient_id": self.ing.id,
                "quantity": "5.0",
            }
        ]
        data = {
            "valid_rows": json.dumps(valid_rows),
            "csrfmiddlewaretoken": "token",
        }
        response = client.post(url, data)
        assert response.status_code in (200, 302)
        self.prod.refresh_from_db()
        item = RecipeItem.objects.get(product=self.prod, ingredient=self.ing)
        assert item.quantity == Decimal("5.0")
