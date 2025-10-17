import pytest
from mscrInventory.models import RecipeItem
from tests.factories import RecipeItemFactory

@pytest.mark.django_db
def test_recipe_item_str():
    item = RecipeItemFactory()
    assert str(item) == f"{item.ingredient.name} ({item.quantity} {item.unit})"

@pytest.mark.django_db
def test_recipe_item_quantity_positive():
    item = RecipeItemFactory(quantity=2.5)
    assert item.quantity > 0
