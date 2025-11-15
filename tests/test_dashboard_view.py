import pytest
from django.urls import reverse
from django.utils import timezone

from tests.factories import (
    ImportLogFactory,
    IngredientFactory,
    ProductFactory,
    RecipeModifierFactory,
    SquareUnmappedItemFactory,
)


@pytest.mark.django_db
def test_dashboard_renders_widgets(client):
    ProductFactory()
    IngredientFactory(name="Beans", current_stock=2, reorder_point=5)
    RecipeModifierFactory()
    SquareUnmappedItemFactory()
    ImportLogFactory(finished_at=timezone.now(), error_count=0, unmatched_count=1)

    response = client.get(reverse("dashboard"))
    assert response.status_code == 200
    content = response.content.decode()

    assert "Active Products" in content
    assert "Tracked Ingredients" in content
    assert "Recent Imports" in content
    assert "Quick Add / Import" in content
    assert "Recent Changes" in content
    assert "Recent Warnings" in content
    assert "Shortcuts" in content


@pytest.mark.django_db
def test_dashboard_warnings_include_low_stock_and_failed_import(client):
    IngredientFactory(name="Espresso", current_stock=1, reorder_point=5)
    SquareUnmappedItemFactory()
    ImportLogFactory(finished_at=timezone.now(), error_count=2, unmatched_count=1)

    response = client.get(reverse("dashboard"))
    content = response.content.decode()

    assert "Inventory running low" in content
    assert "Unmapped Square items" in content
    assert "Import failed" in content

