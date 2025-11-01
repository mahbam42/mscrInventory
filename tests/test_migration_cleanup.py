import importlib

import pytest
from django.apps import apps as django_apps
from django.db import connection

cleanup_orphan_roast_profiles = importlib.import_module(
    "mscrInventory.migrations.0021_recipemodifier_ingredient_type"
).cleanup_orphan_roast_profiles


class StubApps:
    def get_model(self, app_label, model_name):
        return django_apps.get_model(app_label, model_name)


@pytest.mark.django_db
def test_cleanup_orphan_roast_profiles_removes_orphans():
    RoastProfile = django_apps.get_model("mscrInventory", "RoastProfile")
    Ingredient = django_apps.get_model("mscrInventory", "Ingredient")

    roast = RoastProfile.objects.create(name="Ghost Roast", bag_size="11oz", grind="whole")
    roast_id = roast.pk

    constraints_disabled = connection.disable_constraint_checking()
    try:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM mscrInventory_ingredient WHERE id = %s", [roast_id])

        assert not Ingredient.objects.filter(pk=roast_id).exists()
        cleanup_orphan_roast_profiles(StubApps(), None)
    finally:
        if constraints_disabled:
            connection.enable_constraint_checking()

    assert not RoastProfile.objects.filter(pk=roast_id).exists()
