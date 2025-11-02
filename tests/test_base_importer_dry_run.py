import pytest

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
