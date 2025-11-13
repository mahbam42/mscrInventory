import pytest

from mscrInventory.models import Ingredient, IngredientType, Packaging, UnitType


@pytest.mark.django_db
class TestPackagingModel:
    def setup_method(self):
        self.packaging_type = IngredientType.objects.create(name="Packaging")
        self.unit_type = UnitType.objects.create(name="Each", abbreviation="ea")

    def test_creating_packaging_for_existing_ingredient_reuses_parent_row(self):
        ingredient = Ingredient.objects.create(
            name="Inline Packaging",
            type=self.packaging_type,
            unit_type=self.unit_type,
        )

        packaging = Packaging(temp="hot", container=None, multiplier=1.0)
        packaging.ingredient_ptr = ingredient
        packaging.save()

        assert Packaging.objects.filter(pk=ingredient.pk).exists()
        assert Ingredient.objects.filter(name="Inline Packaging").count() == 1

    def test_packaging_save_does_not_clobber_parent_fields(self):
        ingredient = Ingredient.objects.create(
            name="Packaging Parent",
            type=self.packaging_type,
            unit_type=self.unit_type,
            notes="keep me",
        )

        packaging = Packaging(temp="cold", container=None, multiplier=1.5)
        packaging.ingredient_ptr = ingredient
        packaging.save()

        ingredient.refresh_from_db()
        assert ingredient.name == "Packaging Parent"
        assert ingredient.notes == "keep me"

    def test_expands_to_links_other_packaging_ingredients(self):
        cup = Packaging.objects.create(
            name="Cup",
            type=self.packaging_type,
            unit_type=self.unit_type,
        )
        lid = Packaging.objects.create(
            name="Lid",
            type=self.packaging_type,
            unit_type=self.unit_type,
        )

        cup.expands_to.add(lid)

        assert list(cup.expands_to.values_list("name", flat=True)) == ["Lid"]
