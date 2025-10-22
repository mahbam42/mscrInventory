# stub for now
from decimal import Decimal
def test_recipe_cogs_calculation(db, sample_recipe):
    cost = sample_recipe.calculated_cogs
    assert cost > 0
    assert round(cost, 4) == Decimal("12.3400")