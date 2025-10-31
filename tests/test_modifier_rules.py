from decimal import Decimal

import pytest
from django.urls import reverse

from mscrInventory.models import RecipeModifier
from tests.factories import (
    IngredientFactory,
    IngredientTypeFactory,
    RecipeModifierFactory,
    UnitTypeFactory,
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


@pytest.mark.django_db
def test_create_modifier_from_modal(client):
    unit = UnitTypeFactory(name="Ounce", abbreviation="oz")
    ingredient = IngredientFactory()

    url = reverse("create_modifier")
    payload = {
        "create_name": "House Special",
        "create_type": "EXTRA",
        "create_ingredient": str(ingredient.id),
        "create_base_quantity": "1.25",
        "create_unit": str(unit.id),
        "create_cost_per_unit": "0.55",
        "create_price_per_unit": "1.25",
    }

    response = client.post(url, data=payload, HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    trigger_header = response.headers.get("HX-Trigger", "")
    assert "Created modifier House Special" in trigger_header

    modifier = RecipeModifier.objects.get(name="House Special")
    assert modifier.type == "EXTRA"
    assert modifier.ingredient == ingredient
    assert modifier.base_quantity == Decimal("1.25")
    assert modifier.unit == "oz"
    assert modifier.cost_per_unit == Decimal("0.55")
    assert modifier.price_per_unit == Decimal("1.25")
    assert response.context_data["selected_modifier_id"] == modifier.id
