import pytest
from mscrInventory.models import RecipeItem
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
