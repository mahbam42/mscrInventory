import pytest
from mscrInventory.models import (
    Ingredient,
    IngredientType,
    RecipeItem,
    RoastProfile,
    get_or_create_roast_profile,
)
from tests.factories import RecipeItemFactory

@pytest.mark.django_db
def test_recipe_item_str():
    item = RecipeItemFactory()
    expected = f"{item.product.name} - {item.quantity}{item.unit} {item.ingredient.name}"
    assert str(item) == expected
    
@pytest.mark.django_db
def test_recipe_item_quantity_positive():
    item = RecipeItemFactory(quantity=2.5)
    assert item.quantity > 0


@pytest.mark.django_db
def test_roast_profile_signal_and_helper_reuse_existing_parent():
    roast_type = IngredientType.objects.create(name="Roasts")
    ingredient = Ingredient.objects.create(name="House Roast", type=roast_type)

    # Signal should have created the roast profile without duplicating the ingredient row
    profile = RoastProfile.objects.get(pk=ingredient.pk)
    assert profile.ingredient_ptr_id == ingredient.pk

    # Reusing the helper mirrors admin/importer entry points and must not raise IntegrityError
    helper_profile = get_or_create_roast_profile(ingredient)
    assert helper_profile.pk == ingredient.pk
    assert helper_profile.ingredient_ptr_id == ingredient.pk

    # Confirm no duplicate ingredient rows were created during profile attachment
    assert Ingredient.objects.filter(pk=ingredient.pk).count() == 1
