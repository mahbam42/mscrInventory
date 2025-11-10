import pytest
from unittest.mock import patch

from django.urls import reverse

from mscrInventory.utils.modifier_explorer import (
    ModifierExplorerAnalyzer,
    ModifierExplorerReport,
    ModifierInsight,
)
from tests.factories import ProductFactory, RecipeModifierFactory


def build_report(alias_modifier=None):
    known = ModifierInsight(normalized="oat milk", classification="known", total_count=5)
    known.modifier_name = "Oat Milk"
    known.modifier_behavior = "add"
    known.raw_labels.update({"OAT MILK": 3, "Oat milk": 2})
    known.items.update({"Vanilla Latte": 3})

    fuzzy = ModifierInsight(normalized="swt crm", classification="fuzzy", total_count=2)
    fuzzy.fuzzy_matches = []

    unknown = ModifierInsight(normalized="pumpkin dust", classification="unknown", total_count=1)

    alias = ModifierInsight(normalized="sweetcrm", classification="alias", total_count=4)
    if alias_modifier is not None:
        alias.modifier_id = alias_modifier.id
        alias.modifier_name = alias_modifier.name
    else:
        alias.modifier_name = "Sweet Cream"
    alias.modifier_behavior = "add"
    alias.alias_label = "SweetCRM"
    alias.raw_labels.update({"SweetCRM": 4, "sweet crm": 1})

    insights = {
        known.normalized: known,
        alias.normalized: alias,
        fuzzy.normalized: fuzzy,
        unknown.normalized: unknown,
    }
    return ModifierExplorerReport(insights=insights, co_occurrence_pairs={("oat milk", "swt crm"): 2}, source_files=[])


@pytest.mark.django_db
@patch.object(ModifierExplorerAnalyzer, "analyze")
def test_modifier_explorer_view_renders(mock_analyze, client):
    modifier = RecipeModifierFactory(name="Sweet Cream")
    mock_analyze.return_value = build_report(alias_modifier=modifier)

    response = client.get(reverse("modifier_explorer"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Modifier Explorer" in content
    assert "Oat Milk" in content
    assert "Alias token" in content
    assert "Update Alias" in content
    assert f'value="{modifier.id}" selected' in content
    assert "pumpkin dust" in content


@pytest.mark.django_db
@patch.object(ModifierExplorerAnalyzer, "analyze")
def test_modifier_explorer_csv_export(mock_analyze, client):
    RecipeModifierFactory(name="Sweet Cream")
    mock_analyze.return_value = build_report()

    response = client.get(reverse("modifier_explorer"), {"format": "csv"})

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    body = response.content.decode("utf-8")
    assert "oat milk" in body
    assert "alias_label" in body.splitlines()[0]


@pytest.mark.django_db
@patch.object(ModifierExplorerAnalyzer, "analyze")
def test_unknown_modifiers_matching_products_hidden_by_default(mock_analyze, client):
    ProductFactory(name="Pumpkin Dust")
    mock_analyze.return_value = build_report()

    response = client.get(
        reverse("modifier_explorer"),
        {"classification": "unknown"},
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "pumpkin dust" not in content
    assert "Hiding 1 matching product" in content
    assert response.context["matched_unknown_product_count"] == 1
    assert response.context["include_known_products"] is False
    assert response.context["classification_totals"]["unknown"] == 0


@pytest.mark.django_db
@patch.object(ModifierExplorerAnalyzer, "analyze")
def test_unknown_modifiers_matching_products_shown_when_requested(mock_analyze, client):
    ProductFactory(name="Pumpkin Dust")
    mock_analyze.return_value = build_report()

    response = client.get(
        reverse("modifier_explorer"),
        {"classification": "unknown", "include_known_products": "true"},
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "pumpkin dust" in content
    assert "Matches product: Pumpkin Dust" in content
    assert "Showing 1 matching product" in content
    assert response.context["include_known_products"] is True
