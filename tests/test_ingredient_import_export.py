import json
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from mscrInventory.models import Ingredient, IngredientType, UnitType


ING_HEADERS = (
    "id,name,type_id,type_name,unit_type_id,unit_type_name,case_size,reorder_point,average_cost_per_unit,lead_time,notes\n"
)


def _login_with_perms(client, username, perm_codenames):
    user = get_user_model().objects.create_user(username=username, password="pw")
    for codename in perm_codenames:
        perm = Permission.objects.get(
            content_type__app_label="mscrInventory",
            codename=codename,
        )
        user.user_permissions.add(perm)
    client.force_login(user)
    return user


@pytest.mark.django_db
class TestIngredientImportExport:
    """Ingredient dashboard CSV export and import flows."""

    def setup_method(self):
        self.type = IngredientType.objects.create(name="Dairy")
        self.unit = UnitType.objects.create(
            name="Fluid Ounce", abbreviation="fl oz", conversion_to_base=Decimal("1")
        )
        self.ing = Ingredient.objects.create(
            name="Whole Milk",
            type=self.type,
            unit_type=self.unit,
            case_size=12,
            reorder_point=Decimal("1.500"),
            average_cost_per_unit=Decimal("0.7500"),
            lead_time=3,
        )

    def test_export_ingredients_csv_contains_headers_and_values(self, client):
        _login_with_perms(client, "exporter", ["view_ingredient"])
        response = client.get(reverse("export_ingredients_csv"))
        assert response.status_code == 200
        body = response.content.decode("utf-8")
        assert "name,type_id,type_name" in body.splitlines()[0]
        assert "Whole Milk" in body
        assert "Dairy" in body

    def test_import_ingredients_csv_preview_validates_rows(self, client):
        _login_with_perms(client, "importer", ["change_ingredient"])
        csv_text = ING_HEADERS + (
            f"{self.ing.id},Whole Milk,{self.type.id},{self.type.name},{self.unit.id},{self.unit.name},24,2.5,0.8000,5,Updated note\n"
        )
        upload = SimpleUploadedFile("ingredients.csv", csv_text.encode("utf-8"), content_type="text/csv")
        response = client.post(reverse("import_ingredients_csv"), {"file": upload})
        assert response.status_code == 200
        assert response.context["count_valid"] == 1
        assert response.context["count_invalid"] == 0
        row = response.context["valid_rows"][0]
        assert row["name"] == "Whole Milk"
        assert row["operation"] == "update"

    def test_confirm_ingredients_import_creates_and_updates(self, client):
        _login_with_perms(client, "importer", ["change_ingredient"])
        rows = [
            {
                "id": self.ing.id,
                "name": "Whole Milk",
                "type_id": self.type.id,
                "unit_type_id": self.unit.id,
                "case_size": 20,
                "reorder_point": "4.0",
                "average_cost_per_unit": "1.1000",
                "lead_time": 7,
                "notes": "Restocked",
            },
            {
                "id": None,
                "name": "Oat Milk",
                "type_id": self.type.id,
                "unit_type_id": self.unit.id,
                "case_size": 16,
                "reorder_point": "2.0",
                "average_cost_per_unit": "1.3000",
                "lead_time": 5,
                "notes": "New alt",
            },
        ]

        response = client.post(
            reverse("confirm_ingredients_import"),
            {"valid_rows": json.dumps(rows)},
        )
        assert response.status_code == 200

        self.ing.refresh_from_db()
        assert self.ing.case_size == 20
        assert self.ing.reorder_point == Decimal("4.000")
        assert self.ing.average_cost_per_unit == Decimal("1.100000")
        assert self.ing.lead_time == 7

        new_ing = Ingredient.objects.get(name="Oat Milk")
        assert new_ing.case_size == 16
        assert new_ing.reorder_point == Decimal("2.000")
        assert new_ing.unit_type == self.unit
