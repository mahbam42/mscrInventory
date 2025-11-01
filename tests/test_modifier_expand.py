import pytest

from importers._aggregate_usage import resolve_modifier_tree
from tests.factories import (
    IngredientFactory,
    IngredientTypeFactory,
    RecipeModifierFactory,
)


@pytest.mark.django_db
def test_resolve_modifier_tree_preserves_relational_types():
    flavor_type = IngredientTypeFactory(name="Flavor")
    extra_type = IngredientTypeFactory(name="Extra")

    parent = RecipeModifierFactory(
        name="Flavor Combo",
        ingredient=IngredientFactory(name="Vanilla", type=flavor_type),
        ingredient_type=flavor_type,
    )
    child = RecipeModifierFactory(
        name="Extra Shot",
        ingredient=IngredientFactory(name="Espresso", type=extra_type),
        ingredient_type=extra_type,
    )

    parent.expands_to.add(child)

    resolved = resolve_modifier_tree(parent)

    assert parent in resolved
    assert child in resolved
    assert parent.ingredient_type == flavor_type
    assert child.ingredient_type == extra_type
    assert any(mod.ingredient_type == extra_type for mod in resolved)
