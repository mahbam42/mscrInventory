import pytest
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from mscrInventory.utils.dashboard_metrics import get_top_named_drinks

from tests.factories import (
    OrderFactory,
    OrderItemFactory,
    ProductFactory,
)


@pytest.mark.django_db
def test_get_top_named_drinks_aggregates_recent_entries():
    cache.clear()
    now = timezone.now()
    product_a = ProductFactory(name="Latte A")
    product_b = ProductFactory(name="Latte B")
    recent_order = OrderFactory(order_date=now - timedelta(days=2))
    another_order = OrderFactory(order_date=now - timedelta(days=5))

    OrderItemFactory(
        order=recent_order,
        product=product_a,
        quantity=2,
        variant_info={"modifiers": ["name this coffee spooky special", "extra caramel"]},
    )
    OrderItemFactory(
        order=recent_order,
        product=product_a,
        quantity=1,
        variant_info={"modifiers": ["name this coffee spooky special"]},
    )
    OrderItemFactory(
        order=another_order,
        product=product_b,
        quantity=1,
        variant_info={"modifiers": ["name your drink cozy cap"]},
    )

    results = get_top_named_drinks(limit=5, lookback_days=30)

    assert len(results) == 2
    assert results[0]["normalized_label"] == "spooky special"
    assert results[0]["count"] == 3
    assert results[0]["products"] == [product_a.name]
    assert results[1]["normalized_label"] == "cozy cap"


@pytest.mark.django_db
def test_get_top_named_drinks_ignores_out_of_window_and_noise():
    cache.clear()
    now = timezone.now()
    old_order = OrderFactory(order_date=now - timedelta(days=90))
    current_order = OrderFactory(order_date=now - timedelta(days=1))

    OrderItemFactory(
        order=old_order,
        variant_info={"modifiers": ["name your drink dusty", "oat milk"]},
    )
    OrderItemFactory(
        order=current_order,
        variant_info={"modifiers": ["almond milk", "name this coffee fresh start"]},
    )
    OrderItemFactory(
        order=current_order,
        variant_info={"modifiers": ["name your drink"]},
    )

    results = get_top_named_drinks(limit=5, lookback_days=30)

    assert len(results) == 1
    assert results[0]["normalized_label"] == "fresh start"


@pytest.mark.django_db
def test_get_top_named_drinks_includes_orders_url_filters():
    cache.clear()
    now = timezone.now()
    product = ProductFactory(name="Latte A")
    recent_order = OrderFactory(order_date=now - timedelta(days=2))

    OrderItemFactory(
        order=recent_order,
        product=product,
        variant_info={"modifiers": ["name this coffee campfire classic"]},
    )

    results = get_top_named_drinks(limit=5, lookback_days=30)

    assert results
    url = results[0]["orders_url"]
    parsed = urlparse(url)
    assert parsed.path == reverse("orders_dashboard")
    params = parse_qs(parsed.query)
    assert params["preset"] == ["30"]
    assert params["platform"] == ["all"]
    assert params["q"] == ["Campfire Classic"]
    today = timezone.localdate()
    start_date = today - timedelta(days=30)
    assert params["start"] == [start_date.isoformat()]
    assert params["end"] == [today.isoformat()]
    assert params["direction"] == ["desc"]
    assert params["sort"] == ["order_date"]
