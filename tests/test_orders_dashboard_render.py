from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from mscrInventory.models import Order, OrderItem, Product


@pytest.fixture
def authenticated_client(client, django_user_model):
    user = django_user_model.objects.create_user(username="render-tester", password="pass1234")
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_order_items_render_variants_and_modifiers(authenticated_client):
    url = reverse("orders_dashboard")
    now = timezone.now()
    product = Product.objects.create(name="Mocha", sku="MOCHA-1")
    order = Order.objects.create(
        order_id="render-1",
        platform="square",
        order_date=now - timedelta(days=1),
        total_amount=9,
    )
    OrderItem.objects.create(
        order=order,
        product=product,
        quantity=1,
        unit_price=9,
        variant_info={"adjectives": ["iced", "tall"], "modifiers": ["almond milk"]},
    )

    response = authenticated_client.get(url)
    content = response.content
    assert b"Variants" in content
    assert b"Modifiers" in content
    assert b"iced" in content
    assert b"almond milk" in content
    assert b"Line Total" in content
    assert b"$9.00" in content


@pytest.mark.django_db
def test_order_items_render_key_value_fallback(authenticated_client):
    url = reverse("orders_dashboard")
    now = timezone.now()
    product = Product.objects.create(name="Tea", sku="TEA-1")
    order = Order.objects.create(
        order_id="render-2",
        platform="shopify",
        order_date=now - timedelta(days=1),
        total_amount=5,
    )
    OrderItem.objects.create(
        order=order,
        product=product,
        quantity=1,
        unit_price=5,
        variant_info={"size": "Large"},
    )

    response = authenticated_client.get(url)
    assert b"size: Large" in response.content
