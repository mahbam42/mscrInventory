import pytest
from django.urls import reverse
from tests.factories import ProductFactory, IngredientFactory, RecipeItemFactory

@pytest.mark.django_db
def test_edit_recipe_view_loads(client):
    product = ProductFactory()
    url = reverse("edit_recipe", args=[product.id])
    response = client.get(url)
    assert response.status_code == 200
    assert b"Edit Recipe" in response.content

@pytest.mark.django_db
def test_add_recipe_ingredient(client):
    product = ProductFactory()
    ingredient = IngredientFactory()
    url = reverse("add_recipe_ingredient", args=[product.id])
    response = client.post(url, {"ingredient_id": ingredient.id, "quantity": 1, "unit": "oz"})
    assert response.status_code == 200


@pytest.mark.django_db
def test_reporting_dashboard_view(client):
    response = client.get(reverse("reporting_dashboard"))
    assert response.status_code == 200
    assert b"Reporting Dashboard" in response.content
