import pytest
from django.urls import reverse
from tests.factories import ProductFactory, IngredientFactory, RecipeItemFactory

@pytest.mark.django_db
def test_htmx_header_triggers_partial(client):
    product = ProductFactory()
    url = reverse("edit_recipe", args=[product.id])
    response = client.get(url, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert b"modal" in response.content.lower()

