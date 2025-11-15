import logging

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse

from mscrInventory.models import Ingredient, Product, RecipeItem, RecipeModifier
from mscrInventory.views import recipe_modal


def _login_recipe_editor(client, username="recipe-modal-editor"):
    user = get_user_model().objects.create_user(username=username, password="pw")
    perm = Permission.objects.get(
        content_type__app_label="mscrInventory",
        codename="change_recipeitem",
    )
    user.user_permissions.add(perm)
    client.force_login(user)
    return user


@pytest.mark.django_db
def test_add_recipe_ingredient_masks_internal_error(client, monkeypatch, caplog):
    _login_recipe_editor(client, "modal-add")
    product = Product.objects.create(name="Test Drink", sku="TD-001")
    ingredient = Ingredient.objects.create(name="Test Ingredient")
    caplog.set_level(logging.ERROR, logger="mscrInventory.views.recipe_modal")

    def boom(*args, **kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(RecipeItem.objects, "create", boom)

    response = client.post(
        reverse("add_recipe_ingredient", args=[product.pk]),
        {"ingredient_id": ingredient.pk, "quantity": "1", "unit": "unit"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "Unable to add ingredient right now."
    assert "boom" not in response.content.decode("utf-8")
    assert any("Failed to add ingredient" in record.getMessage() for record in caplog.records)


@pytest.mark.django_db
def test_save_recipe_modifiers_masks_internal_error(client, monkeypatch, caplog):
    _login_recipe_editor(client, "modal-save")
    product = Product.objects.create(name="Another Drink", sku="AD-001")
    caplog.set_level(logging.ERROR, logger="mscrInventory.views.recipe_modal")

    def boom_filter(*args, **kwargs):
        raise ValueError("boom")

    monkeypatch.setattr(RecipeModifier.objects, "filter", boom_filter)

    response = client.post(
        reverse("save_recipe_modifiers", args=[product.pk]),
        {"modifiers": ["1"]},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "Unable to save modifiers right now."
    assert "boom" not in response.content.decode("utf-8")
    assert any("Failed to save modifiers" in record.getMessage() for record in caplog.records)


def test_log_import_appends(tmp_path, monkeypatch):
    log_file = tmp_path / "recipes.log"
    monkeypatch.setattr(recipe_modal, "LOG_FILE", log_file)

    recipe_modal.log_import("IMPORT", "first entry")
    recipe_modal.log_import("IMPORT", "second entry")

    contents = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(contents) == 2
    assert "first entry" in contents[0]
    assert "second entry" in contents[1]
