import factory
from mscrInventory.models import Product, Ingredient, RecipeItem

class IngredientFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Ingredient

    name = factory.Faker("word")
    type = "base"
    unit_type = "oz"

class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product

    name = factory.Faker("word")

class RecipeItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = RecipeItem

    product = factory.SubFactory(ProductFactory)
    ingredient = factory.SubFactory(IngredientFactory)
    quantity = 1
    unit = "oz"
