import os
import django
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

# Only initialize once
if not django.apps.apps.ready:
    django.setup()

import pytest
from decimal import Decimal
from mscrInventory.models import Ingredient, Product, RecipeItem

@pytest.fixture
def sample_recipe(db):
    prod = Product.objects.create(name="Latte")
    ing = Ingredient.objects.create(name="Milk", average_cost_per_unit=Decimal("0.50"))
    
    RecipeItem.objects.create(product=prod, ingredient=ing, quantity=Decimal("2.0"))
    return prod

