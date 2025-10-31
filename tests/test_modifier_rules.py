from decimal import Decimal

import pytest
from django.urls import reverse

from mscrInventory.models import RecipeModifier
from tests.factories import (
    IngredientFactory,
    IngredientTypeFactory,
    RecipeModifierFactory,
)


@pytest.mark.django_db
def test_modifier_rules_modal_get(client):
    RecipeModifierFactory()
    url = reverse("modifier_rules_modal")
    response = client.get(url, HTTP_HX_REQUEST="true")
    assert response.status_code == 200
    assert b"Edit Modifier Rules" in response.content


@pytest.mark.django_db
def test_modifier_rules_modal_updates_modifier(client):
    milk_type = IngredientTypeFactory(name="MILK")
    target_ingredient = IngredientFactory(name="Bacon", type=milk_type)
    modifier = RecipeModifierFactory(name="House Modifier")
    other_modifier = RecipeModifierFactory(name="Extra Shot", type="EXTRA")

    url = reverse("modifier_rules_modal")
    payload = {
        "modifier_id": modifier.id,
        "behavior": RecipeModifier.ModifierBehavior.REPLACE,
        "quantity_factor": "1.50",
        "target_by_type": ["MILK"],
        "target_by_name": [target_ingredient.name],
        "replacement_name": ["Oat Milk"],
        "replacement_qty": ["1.0"],
        "expands_to": [str(other_modifier.id)],
    }

    response = client.post(url, data=payload, HTTP_HX_REQUEST="true")
    assert response.status_code == 200

    modifier.refresh_from_db()
    assert modifier.behavior == RecipeModifier.ModifierBehavior.REPLACE
    assert modifier.quantity_factor == Decimal("1.50")
    assert modifier.target_selector == {
        "by_type": ["MILK"],
        "by_name": [target_ingredient.name],
    }
    assert modifier.replaces == {"to": [["Oat Milk", 1.0]]}
    assert list(modifier.expands_to.values_list("id", flat=True)) == [other_modifier.id]
