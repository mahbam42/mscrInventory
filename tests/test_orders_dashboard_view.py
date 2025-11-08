from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from mscrInventory.models import Order, OrderItem, Product


@pytest.fixture
def authenticated_client(client, django_user_model):
    user = django_user_model.objects.create_user(username="tester", password="pass1234")
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_orders_dashboard_filters(authenticated_client):
    url = reverse("orders_dashboard")
    now = timezone.now()

    recent_square = Order.objects.create(
        order_id="recent-square",
        platform="square",
        order_date=now - timedelta(days=1),
        total_amount=10,
        synced_at=now,
    )
    recent_shopify = Order.objects.create(
        order_id="recent-shopify",
        platform="shopify",
        order_date=now - timedelta(days=2),
        total_amount=12,
        synced_at=now,
    )
    outside_range = Order.objects.create(
        order_id="older",
        platform="square",
        order_date=now - timedelta(days=40),
        total_amount=5,
    )
    custom_window = Order.objects.create(
        order_id="custom",
        platform="square",
        order_date=now - timedelta(days=25),
        total_amount=8,
    )

    response = authenticated_client.get(url)
    assert response.status_code == 200
    orders = list(response.context["orders"])
    assert recent_square in orders
    assert recent_shopify in orders
    assert outside_range not in orders
    assert response.context["selected_preset"] == "14"

    response_platform = authenticated_client.get(url, {"platform": "shopify"})
    platform_orders = list(response_platform.context["orders"])
    assert recent_shopify in platform_orders
    assert recent_square not in platform_orders

    start_date = (timezone.localdate() - timedelta(days=28)).isoformat()
    end_date = (timezone.localdate() - timedelta(days=20)).isoformat()
    response_custom = authenticated_client.get(
        url,
        {"preset": "custom", "start": start_date, "end": end_date},
    )
    custom_orders = list(response_custom.context["orders"])
    assert custom_window in custom_orders
    assert response_custom.context["show_custom_range"] is True
    assert str(response_custom.context["start_date"]) == start_date
    assert str(response_custom.context["end_date"]) == end_date


@pytest.mark.django_db
def test_orders_dashboard_pagination(authenticated_client):
    url = reverse("orders_dashboard")
    now = timezone.now()
    for idx in range(30):
        Order.objects.create(
            order_id=f"order-{idx}",
            platform="square",
            order_date=now - timedelta(hours=idx % 5),
            total_amount=idx,
        )

    response_page1 = authenticated_client.get(url, {"platform": "square", "preset": "14"})
    assert response_page1.status_code == 200
    assert len(response_page1.context["orders"]) == 25

    response_page2 = authenticated_client.get(
        url,
        {"platform": "square", "preset": "14", "page": 2},
    )
    page_obj = response_page2.context["page_obj"]
    assert page_obj.number == 2
    assert len(response_page2.context["orders"]) == 5
    querystring = response_page2.context["querystring"]
    assert "platform=square" in querystring
    assert "preset=14" in querystring


@pytest.mark.django_db
def test_orders_dashboard_total_items_annotation(authenticated_client):
    url = reverse("orders_dashboard")
    now = timezone.now()
    product = Product.objects.create(name="Latte", sku="LATTE-1")
    order = Order.objects.create(
        order_id="annotated",
        platform="square",
        order_date=now,
        total_amount=15,
    )
    OrderItem.objects.create(order=order, product=product, quantity=2, unit_price=5)
    OrderItem.objects.create(order=order, product=product, quantity=3, unit_price=1)

    response = authenticated_client.get(url)
    annotated_order = next(o for o in response.context["orders"] if o.pk == order.pk)
    assert annotated_order.total_items == 5


@pytest.mark.django_db
def test_orders_dashboard_search(authenticated_client):
    url = reverse("orders_dashboard")
    now = timezone.now()
    product = Product.objects.create(name="Matcha", sku="MATCHA-1")

    order_matcha = Order.objects.create(
        order_id="order-1001",
        platform="square",
        order_date=now,
        total_amount="12.50",
    )
    OrderItem.objects.create(
        order=order_matcha,
        product=product,
        quantity=1,
        unit_price="12.50",
        variant_info={"modifiers": ["extra vanilla"]},
    )

    other_order = Order.objects.create(
        order_id="order-1002",
        platform="shopify",
        order_date=now,
        total_amount="9.00",
    )

    # Order ID search
    response = authenticated_client.get(url, {"q": "1001"})
    orders = list(response.context["orders"])
    assert order_matcha in orders
    assert other_order not in orders

    # Product name search
    response = authenticated_client.get(url, {"q": "Matcha"})
    orders = list(response.context["orders"])
    assert order_matcha in orders

    # Modifier search
    response = authenticated_client.get(url, {"q": "vanilla"})
    orders = list(response.context["orders"])
    assert order_matcha in orders

    # Total search
    response = authenticated_client.get(url, {"q": "12.50"})
    orders = list(response.context["orders"])
    assert order_matcha in orders


@pytest.mark.django_db
def test_orders_dashboard_sorting(authenticated_client):
    url = reverse("orders_dashboard")
    now = timezone.now()

    low = Order.objects.create(order_id="a", platform="square", order_date=now, total_amount="5.00")
    mid = Order.objects.create(order_id="b", platform="square", order_date=now - timedelta(hours=1), total_amount="10.00")
    high = Order.objects.create(order_id="c", platform="square", order_date=now - timedelta(hours=2), total_amount="15.00")

    response = authenticated_client.get(url, {"sort": "total", "direction": "asc"})
    ordered_ids = [order.order_id for order in response.context["orders"][:3]]
    assert ordered_ids[:3] == [low.order_id, mid.order_id, high.order_id]

    response_desc = authenticated_client.get(url, {"sort": "total", "direction": "desc"})
    ordered_ids_desc = [order.order_id for order in response_desc.context["orders"][:3]]
    assert ordered_ids_desc[:3] == [high.order_id, mid.order_id, low.order_id]
