import pytest

from pathlib import Path
import datetime

from importers._base_Importer import BaseImporter
from mscrInventory.models import Ingredient


@pytest.mark.django_db
def test_create_or_update_dry_run_does_not_touch_db():
    importer = BaseImporter(dry_run=True, log_to_console=False)

    obj, created = importer.create_or_update(
        Ingredient,
        {"name": "Test Ingredient"},
        {"notes": "Example"},
    )

    assert created is True
    assert obj.pk is None
    assert Ingredient.objects.filter(name="Test Ingredient").count() == 0
    assert importer.counters["added"] == 1


@pytest.mark.django_db
def test_create_or_update_dry_run_skips_updates():
    existing = Ingredient.objects.create(name="Milk")

    importer = BaseImporter(dry_run=True, log_to_console=False)
    obj, created = importer.create_or_update(
        Ingredient,
        {"name": "Milk"},
        {"notes": "Updated"},
    )

    assert created is False
    assert obj.pk == existing.pk
    existing.refresh_from_db()
    assert existing.notes == ""
    assert importer.counters["updated"] == 1


@pytest.mark.django_db
def test_create_or_update_live_persists_changes():
    importer = BaseImporter(dry_run=False, log_to_console=False)
    obj, created = importer.create_or_update(
        Ingredient,
        {"name": "Real Ingredient"},
        {"notes": "Saved"},
    )

    assert created is True
    assert obj.pk is not None
    obj.refresh_from_db()
    assert obj.notes == "Saved"


@pytest.mark.django_db
def test_base_importer_report(tmp_path):
    report_dir = tmp_path / "reports"
    importer = BaseImporter(
        dry_run=True,
        log_to_console=False,
        report=True,
        report_dir=report_dir,
    )

    fake_date = datetime.date(2024, 1, 1)
    importer.report_date = fake_date
    importer.summarize()

    expected = Path(report_dir) / "2024-01-01.csv"
    assert expected.exists()

    content = expected.read_text().splitlines()
    assert content[0] == "metric,value"
