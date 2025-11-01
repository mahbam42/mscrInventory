import pytest

from mscrInventory.models import IngredientType, RecipeModifier
from tests.factories import IngredientFactory, IngredientTypeFactory, RecipeModifierFactory


@pytest.mark.django_db
def test_recipe_modifier_links_to_ingredient_type():
    milk_type = IngredientTypeFactory(name="Milk")
    flavor_type = IngredientTypeFactory(name="Flavor")

    milk_modifier = RecipeModifierFactory(
        name="Whole Milk",
        ingredient=IngredientFactory(name="Whole Milk Ingredient", type=milk_type),
        ingredient_type=milk_type,
    )
    flavor_modifier = RecipeModifierFactory(
        name="Vanilla Syrup",
        ingredient=IngredientFactory(name="Vanilla Syrup Ingredient", type=flavor_type),
        ingredient_type=flavor_type,
    )

    assert milk_modifier.ingredient_type == milk_type
    assert flavor_modifier.ingredient_type == flavor_type
    assert list(milk_type.recipe_modifiers.values_list("name", flat=True)) == [milk_modifier.name]
    assert flavor_modifier.name in list(flavor_type.recipe_modifiers.values_list("name", flat=True))
    assert str(milk_modifier).endswith("(Milk)")


@pytest.mark.django_db
def test_category_creation_reuses_existing_type():
    existing = IngredientType.objects.create(name="Syrup")

    modifier = RecipeModifierFactory(
        name="Caramel Syrup",
        ingredient=IngredientFactory(name="Caramel Ingredient", type=existing),
        ingredient_type=existing,
    )

    assert modifier.ingredient_type_id == existing.id
    assert IngredientType.objects.filter(name="Syrup").count() == 1
