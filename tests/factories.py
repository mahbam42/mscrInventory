import factory
from mscrInventory.models import (
    Ingredient,
    IngredientType,
    Product,
    RecipeItem,
    RecipeModifier,
)

class IngredientTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IngredientType
    name = factory.Sequence(lambda n: f"Type {n}")

class IngredientFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Ingredient
    name = factory.Sequence(lambda n: f"Ingredient {n}")
    type = factory.SubFactory(IngredientTypeFactory)  # ✅ required
    average_cost_per_unit = 1.00
    current_stock = 10

class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product
    name = factory.Sequence(lambda n: f"Product {n}")

class RecipeItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RecipeItem
    product = factory.SubFactory(ProductFactory)
    ingredient = factory.SubFactory(IngredientFactory)
    quantity = 2.5


class RecipeModifierFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RecipeModifier

    name = factory.Sequence(lambda n: f"Modifier {n}")
    type = "MILK"
    behavior = RecipeModifier.ModifierBehavior.ADD
    ingredient = factory.SubFactory(IngredientFactory)
    base_quantity = 1
    unit = "oz"
    cost_per_unit = 0
    price_per_unit = 0