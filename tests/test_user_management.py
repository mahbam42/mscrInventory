import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import RequestFactory
from django.urls import reverse

from core.context_processors import navigation_links


@pytest.fixture
def change_user_permission(db):
    return Permission.objects.get(
        content_type__app_label="auth",
        codename="change_user",
    )


@pytest.mark.django_db
def test_manage_users_requires_permission(client):
    user = get_user_model().objects.create_user("barista", password="pw")
    client.force_login(user)

    response = client.get(reverse("manage_users"))
    assert response.status_code == 403


@pytest.mark.django_db
def test_manage_users_can_create_user(client, change_user_permission):
    manager = get_user_model().objects.create_user("manager", password="pw", is_staff=True)
    manager.user_permissions.add(change_user_permission)
    client.force_login(manager)

    payload = {
        "action": "create",
        "create-username": "newhire",
        "create-email": "newhire@example.com",
        "create-is_active": "on",
        "create-password1": "Sup3rSecret!",
        "create-password2": "Sup3rSecret!",
    }
    response = client.post(reverse("manage_users"), payload)

    assert response.status_code == 302
    created = get_user_model().objects.get(username="newhire")
    assert created.email == "newhire@example.com"
    assert created.is_active


@pytest.mark.django_db
def test_manage_users_can_reset_password(client, change_user_permission):
    manager = get_user_model().objects.create_user("lead", password="pw", is_staff=True)
    manager.user_permissions.add(change_user_permission)
    client.force_login(manager)

    target = get_user_model().objects.create_user("barista", password="old-pass", is_active=True)

    payload = {
        "action": "update",
        "user_id": str(target.pk),
        "edit-username": target.username,
        "edit-email": "",
        "edit-is_active": "on",
        "edit-password1": "N3wPassphrase!",
        "edit-password2": "N3wPassphrase!",
    }
    response = client.post(f"{reverse('manage_users')}?user={target.pk}", payload)
    assert response.status_code == 302

    target.refresh_from_db()
    assert target.check_password("N3wPassphrase!")


@pytest.mark.django_db
def test_navigation_links_include_admin_and_manage_users(change_user_permission):
    factory = RequestFactory()
    user = get_user_model().objects.create_user("nav-manager", password="pw", is_staff=True)
    user.user_permissions.add(change_user_permission)
    request = factory.get("/")
    request.user = user

    context = navigation_links(request)
    names = [link["name"] for link in context["nav_links"]]

    assert "Manage Users" in names
    assert "Admin" in names


@pytest.mark.django_db
def test_navigation_links_hide_manage_users_without_change_perm():
    factory = RequestFactory()
    user = get_user_model().objects.create_user("nav-barista", password="pw")
    view_user_perm = Permission.objects.get(
        content_type__app_label="auth", codename="view_user"
    )
    user.user_permissions.add(view_user_perm)

    request = factory.get("/")
    request.user = user

    context = navigation_links(request)
    names = [link["name"] for link in context["nav_links"]]

    assert "Manage Users" not in names


@pytest.mark.django_db
def test_navigation_links_hide_reporting_without_permission():
    factory = RequestFactory()
    user = get_user_model().objects.create_user("nav-no-report", password="pw")

    request = factory.get("/")
    request.user = user

    context = navigation_links(request)
    names = [link["name"] for link in context["nav_links"]]

    assert "Reporting" not in names
