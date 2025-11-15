from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from tests.factories import (
    ImportLogFactory,
    IngredientFactory,
    ProductFactory,
    RecipeModifierFactory,
    SquareUnmappedItemFactory,
)


@pytest.mark.django_db
@patch("mscrInventory.views.dashboard.get_top_named_drinks")
def test_dashboard_renders_widgets(mock_named_drinks, client):
    mock_named_drinks.return_value = [
        {
            "label": "Dracula's Delight",
            "normalized_label": "draculas delight",
            "count": 3,
            "products": ["Latte"],
            "last_seen": timezone.now(),
            "orders_url": "/orders/?preset=30&platform=all&q=Dracula&start=2025-10-17&end=2025-11-15&sort=order_date&direction=desc",
        }
    ]
    ProductFactory()
    IngredientFactory(name="Beans", current_stock=2, reorder_point=5)
    RecipeModifierFactory()
    SquareUnmappedItemFactory()
    ImportLogFactory(finished_at=timezone.now(), error_count=0, unmatched_count=1)

    user = get_user_model().objects.create_user("tester", password="pw")
    client.force_login(user)

    response = client.get(reverse("dashboard"))
    assert response.status_code == 200
    content = response.content.decode()

    assert "Active Products" in content
    assert "Tracked Ingredients" in content
    assert "Recent Imports" in content
    assert "Quick Add / Import" in content
    assert "Recent Changes" in content
    assert "Top Name-Your-Drink" in content
    assert escape("Dracula's Delight") in content
    assert "orders/?preset=30" in content
    assert "Recent Warnings" in content
    assert "Shortcuts" in content


@pytest.mark.django_db
def test_dashboard_warnings_include_low_stock_and_failed_import(client):
    IngredientFactory(name="Espresso", current_stock=1, reorder_point=5)
    SquareUnmappedItemFactory()
    ImportLogFactory(finished_at=timezone.now(), error_count=2, unmatched_count=1)

    user = get_user_model().objects.create_user("manager", password="pw")
    client.force_login(user)

    response = client.get(reverse("dashboard"))
    content = response.content.decode()

    assert "Inventory running low" in content
    assert "Unmapped Square items" in content
    assert "Import failed" in content

