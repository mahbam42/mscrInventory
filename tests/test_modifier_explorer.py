import pytest

from mscrInventory.models import RecipeModifier, RecipeModifierAlias
from mscrInventory.utils.modifier_explorer import ModifierExplorerAnalyzer
from tests.factories import RecipeModifierFactory


@pytest.fixture
def csv_file(tmp_path):
    content = """Item,Modifiers Applied
Vanilla Latte,"Oat Milk, Vanilla"
Cold Brew,"Extra Shot, Iced"
Vanilla Latte,"OAT MILK"
Pumpkin Latte,"Pumpkin Spice"
"""
    csv_path = tmp_path / "sample.csv"
    csv_path.write_text(content)
    return csv_path


def test_analyzer_counts_and_classification(db, csv_file):
    modifier = RecipeModifierFactory(name="Oat Milk", behavior=RecipeModifier.ModifierBehavior.ADD)

    analyzer = ModifierExplorerAnalyzer()
    report = analyzer.analyze(paths=[csv_file])

    assert csv_file in report.source_files
    oat = report.insights["oat milk"]
    assert oat.total_count == 2
    assert oat.classification == "known"
    assert oat.modifier_id == modifier.id
    assert oat.modifier_behavior == modifier.behavior

    vanilla = report.insights["vanilla"]
    assert vanilla.total_count == 1
    assert vanilla.classification == "unknown"


def test_analyzer_ignores_temperature_tokens(db, tmp_path):
    content = """Item,Modifiers Applied
Cold Brew,"iced, extra shot"
"""
    csv_path = tmp_path / "test.csv"
    csv_path.write_text(content)

    RecipeModifierFactory(name="Extra Shot", behavior=RecipeModifier.ModifierBehavior.ADD)

    analyzer = ModifierExplorerAnalyzer()
    report = analyzer.analyze(paths=[csv_path])

    assert "iced" not in report.insights
    assert report.insights["extra shot"].total_count == 1


def test_analyzer_co_occurrence(db, tmp_path):
    content = """Item,Modifiers Applied
Latte,"Oat Milk, Vanilla, Extra Shot"
"""
    csv_path = tmp_path / "co.csv"
    csv_path.write_text(content)

    RecipeModifierFactory(name="Oat Milk")

    analyzer = ModifierExplorerAnalyzer()
    report = analyzer.analyze(paths=[csv_path])

    oat = report.insights["oat milk"]
    assert oat.co_occurrence["extra shot"] == 1
    assert ("extra shot", "vanilla") in report.co_occurrence_pairs


def test_analyzer_marks_aliases(db, tmp_path):
    content = """Item,Modifiers Applied
Latte,"SweetCRM"
"""
    csv_path = tmp_path / "alias.csv"
    csv_path.write_text(content)

    modifier = RecipeModifierFactory(name="Sweet Cream")
    RecipeModifierAlias.objects.create(modifier=modifier, raw_label="SweetCRM")

    analyzer = ModifierExplorerAnalyzer()
    report = analyzer.analyze(paths=[csv_path])

    entry = report.insights["sweetcrm"]
    assert entry.classification == "alias"
    assert entry.modifier_id == modifier.id
    assert entry.alias_label == "SweetCRM"
