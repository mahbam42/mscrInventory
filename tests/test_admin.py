import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from mscrInventory import admin as admin_module
from mscrInventory.models import Ingredient, IngredientType, Packaging, UnitType


@pytest.mark.django_db
class TestIngredientAdminPackagingInline:
    def setup_method(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="password123",
        )
        self.request = RequestFactory().get("/admin/mscrInventory/ingredient/1/change/")
        self.request.user = self.user
        self.ingredient_admin = admin_module.IngredientAdmin(Ingredient, admin.site)

    def test_packaging_inline_added_once_with_expected_limits(self):
        packaging_type = IngredientType.objects.create(name="Packaging")
        unit_type = UnitType.objects.create(name="Each", abbreviation="ea")
        packaging = Packaging.objects.create(
            name="12oz Hot Cup",
            type=packaging_type,
            unit_type=unit_type,
        )

        inline_instances = self.ingredient_admin.get_inline_instances(self.request, packaging)
        packaging_inlines = [
            inline for inline in inline_instances if isinstance(inline, admin_module.PackagingInline)
        ]

        assert len(packaging_inlines) == 1
        inline = packaging_inlines[0]
        assert inline.extra == 0
        assert inline.can_delete is False
        assert inline.max_num == 1

    def test_packaging_inline_not_added_for_non_packaging_ingredients(self):
        other_type = IngredientType.objects.create(name="Coffee")
        ingredient = Ingredient.objects.create(name="Test Ingredient", type=other_type)

        inline_instances = self.ingredient_admin.get_inline_instances(self.request, ingredient)
        assert all(
            not isinstance(inline, admin_module.PackagingInline)
            for inline in inline_instances
        )

    def test_packaging_inline_expands_to_queryset_filters_packaging(self):
        packaging_type, _ = IngredientType.objects.get_or_create(name="Packaging")
        other_type = IngredientType.objects.create(name="Coffee")
        unit_type, _ = UnitType.objects.get_or_create(name="Each", defaults={"abbreviation": "ea"})

        cup = Packaging.objects.create(
            name="Paper Cup",
            type=packaging_type,
            unit_type=unit_type,
        )
        lid = Packaging.objects.create(
            name="Cup Lid",
            type=packaging_type,
            unit_type=unit_type,
        )
        other = Ingredient.objects.create(name="Espresso Beans", type=other_type)

        inline = admin_module.PackagingInline(Ingredient, admin.site)
        field = inline.formfield_for_manytomany(
            Packaging._meta.get_field("expands_to"),
            self.request,
        )

        queryset = field.queryset
        assert queryset.filter(pk=cup.pk).exists()
        assert queryset.filter(pk=lid.pk).exists()
        assert not queryset.filter(pk=other.pk).exists()

