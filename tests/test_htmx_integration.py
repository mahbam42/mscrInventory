import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from tests.factories import ProductFactory


def _login_recipe_viewer(client):
    user = get_user_model().objects.create_user("htmx-viewer", password="pw")
    perm = Permission.objects.get(codename="view_product")
    user.user_permissions.add(perm)
    client.force_login(user)


@pytest.mark.django_db
def test_htmx_header_triggers_partial(client):
    _login_recipe_viewer(client)
    product = ProductFactory()
    url = reverse("edit_recipe", args=[product.id])
    response = client.get(url, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert b"modal" in response.content.lower()
