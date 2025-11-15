import datetime
from decimal import Decimal

import pytest
import datetime
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.urls import reverse
from django.utils import timezone

from mscrInventory.models import Order, OrderItem
from tests.factories import (
    CategoryFactory,
    IngredientFactory,
    ProductFactory,
    RecipeItemFactory,
)


def _login_user(client, username="views-user", perm_codenames=None):
    user = get_user_model().objects.create_user(username=username, password="pw")
    for codename in perm_codenames or []:
        perm = Permission.objects.get(
            content_type__app_label="mscrInventory",
            codename=codename,
        )
        user.user_permissions.add(perm)
    client.force_login(user)
    return user

@pytest.mark.django_db
def test_edit_recipe_view_loads(client):
    _login_user(client, "views-recipes", ["view_product"])
    product = ProductFactory()
    url = reverse("edit_recipe", args=[product.id])
    response = client.get(url)
    assert response.status_code == 200
    assert b"Edit Recipe" in response.content

@pytest.mark.django_db
def test_add_recipe_ingredient(client):
    _login_user(client, "views-recipe", ["change_recipeitem"])
    product = ProductFactory()
    ingredient = IngredientFactory()
    url = reverse("add_recipe_ingredient", args=[product.id])
    response = client.post(url, {"ingredient_id": ingredient.id, "quantity": 1, "unit": "oz"})
    assert response.status_code == 200


@pytest.mark.django_db
def test_reporting_dashboard_view(client):
    _login_user(client, "views-report", ["change_order"])
    response = client.get(reverse("reporting_dashboard"))
    assert response.status_code == 200
    assert b"Reporting Dashboard" in response.content


@pytest.mark.django_db
def test_reporting_dashboard_shows_variant_modal_trigger(client):
    _login_user(client, "views-report-variants", ["change_order"])
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
def test_reporting_dashboard_requires_permission(client):
    _login_user(client, "views-report-no-perms")

    response = client.get(reverse("reporting_dashboard"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_recipes_dashboard_filters_uncategorised(client):
    _login_user(client, "views-recipes-dashboard", ["view_product"])
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
    _login_user(client, "views-recipes-fragment", ["view_product"])
    uncategorised = ProductFactory(name="Americano Solo")
    category = CategoryFactory(name="Signature")
    categorized = ProductFactory(name="Signature Latte")
    categorized.categories.add(category)

    response = client.get(reverse("recipes_table_fragment"), {"category": "none"})

    content = response.content.decode("utf-8")
    assert "Americano Solo" in content
    assert "Signature Latte" not in content


@pytest.mark.django_db
def test_dashboard_renders_user_banner(client):
    group = Group.objects.create(name="Manager")
    user = get_user_model().objects.create_user("banner-user", password="pw")
    user.groups.add(group)
    client.force_login(user)

    response = client.get(reverse("dashboard"))
    content = response.content.decode("utf-8")

    assert "Logout" in content
    assert "Manager" in content
    assert 'data-user-role="Manager"' in content
