import pytest
from unittest.mock import patch

from django.urls import reverse

from mscrInventory.utils.modifier_explorer import (
    ModifierExplorerAnalyzer,
    ModifierExplorerReport,
    ModifierInsight,
)
from tests.factories import RecipeModifierFactory


def build_report():
    known = ModifierInsight(normalized="oat milk", classification="known", total_count=5)
    known.modifier_name = "Oat Milk"
    known.modifier_behavior = "add"
    known.raw_labels.update({"OAT MILK": 3, "Oat milk": 2})
    known.items.update({"Vanilla Latte": 3})

    fuzzy = ModifierInsight(normalized="swt crm", classification="fuzzy", total_count=2)
    fuzzy.fuzzy_matches = []

    unknown = ModifierInsight(normalized="pumpkin dust", classification="unknown", total_count=1)

    alias = ModifierInsight(normalized="sweetcrm", classification="alias", total_count=4)
    alias.modifier_name = "Sweet Cream"
    alias.modifier_behavior = "add"
    alias.alias_label = "SweetCRM"
    alias.raw_labels.update({"SweetCRM": 4})

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
    RecipeModifierFactory(name="Sweet Cream")
    mock_analyze.return_value = build_report()

    response = client.get(reverse("modifier_explorer"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Modifier Explorer" in content
    assert "Oat Milk" in content
    assert "Alias token" in content
    assert "Add Alias" in content
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
