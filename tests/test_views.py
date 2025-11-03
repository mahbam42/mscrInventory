import pytest
from django.urls import reverse
from tests.factories import (
    CategoryFactory,
    IngredientFactory,
    ProductFactory,
    RecipeItemFactory,
)

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


@pytest.mark.django_db
def test_recipes_dashboard_filters_uncategorised(client):
    uncategorised = ProductFactory(name="Lonely Latte")
    category = CategoryFactory(name="Seasonal")
    categorized = ProductFactory(name="Pumpkin Spice")
    categorized.categories.add(category)

    response = client.get(reverse("recipes_dashboard"), {"category": "none"})

    content = response.content.decode("utf-8")
    assert "Lonely Latte" in content
    assert "Pumpkin Spice" not in content


@pytest.mark.django_db
def test_recipes_table_fragment_respects_none_filter(client):
    uncategorised = ProductFactory(name="Americano Solo")
    category = CategoryFactory(name="Signature")
    categorized = ProductFactory(name="Signature Latte")
    categorized.categories.add(category)

    response = client.get(reverse("recipes_table_fragment"), {"category": "none"})

    content = response.content.decode("utf-8")
    assert "Americano Solo" in content
    assert "Signature Latte" not in content
