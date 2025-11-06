import datetime
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from mscrInventory.models import Order, OrderItem
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
def test_reporting_dashboard_shows_variant_modal_trigger(client):
    product = ProductFactory(name="Cookie Sampler")
    order = Order.objects.create(
        order_id="order-1",
        platform="square",
        order_date=timezone.make_aware(datetime.datetime(2024, 1, 5, 9, 0)),
        total_amount=Decimal("0.00"),
    )
    OrderItem.objects.create(
        order=order,
        product=product,
        quantity=2,
        unit_price=Decimal("4.00"),
        variant_info={"modifiers": ["oat milk"]},
    )
    OrderItem.objects.create(
        order=order,
        product=product,
        quantity=3,
        unit_price=Decimal("4.50"),
        variant_info={"modifiers": ["almond milk"]},
    )

    response = client.get(reverse("reporting_dashboard"))
    content = response.content.decode("utf-8")
    assert "variant-details-" in content
    assert "data-variant-script-id" in content


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
