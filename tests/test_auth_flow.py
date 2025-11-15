import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.urls import reverse


@pytest.mark.django_db
def test_root_redirects_to_login(client):
    response = client.get("/", follow=True)
    # expect redirect chain: / -> /dashboard/ -> /login/
    final_url, status_code = response.redirect_chain[-1]
    assert "/login/" in final_url
    assert status_code == 302
    assert response.status_code == 200


@pytest.mark.django_db
def test_logout_clears_session(client):
    User = get_user_model()
    user = User.objects.create_user("tester", password="pass123")
    client.force_login(user)

    response = client.get(reverse("dashboard"))
    assert response.status_code == 200

    logout_response = client.get(reverse("logout"))
    assert logout_response.status_code == 302
    assert logout_response.headers["Location"].endswith("/login/")

    # accessing dashboard should now redirect to login
    follow_up = client.get(reverse("dashboard"))
    assert follow_up.status_code == 302
    assert "/login/" in follow_up.headers["Location"]


@pytest.mark.django_db
def test_anonymous_user_cannot_access_imports_dashboard(client):
    response = client.get(reverse("imports_dashboard"))
    assert response.status_code == 302
    assert "/login/" in response.headers["Location"]


@pytest.mark.django_db
def test_barista_can_log_in_without_staff_flag(client):
    User = get_user_model()
    barista_group, _ = Group.objects.get_or_create(name="Barista")
    user = User.objects.create_user("barista", password="beans123")
    user.groups.add(barista_group)

    response = client.post(
        reverse("login"), {"username": "barista", "password": "beans123"}, follow=True
    )

    assert response.wsgi_request.user.is_authenticated
    assert response.redirect_chain[-1][0].endswith("/dashboard/")


@pytest.mark.django_db
def test_modifier_explorer_link_respects_permissions(client):
    User = get_user_model()
    user = User.objects.create_user("viewer", password="pass123")
    view_ingredient = Permission.objects.get(codename="view_ingredient")
    user.user_permissions.add(view_ingredient)
    client.force_login(user)

    response = client.get(reverse("imports_dashboard"))
    content = response.content.decode()
    assert "Open Explorer" not in content

    view_modifier = Permission.objects.get(codename="view_recipemodifier")
    user.user_permissions.add(view_modifier)
    response_with_perm = client.get(reverse("imports_dashboard"))
    assert "Open Explorer" in response_with_perm.content.decode()
