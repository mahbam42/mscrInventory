import factory
from mscrInventory.models import Product, Ingredient, RecipeItem, IngredientType

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