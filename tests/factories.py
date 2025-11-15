import factory
from django.utils import timezone

from mscrInventory.models import (
    Category,
    ImportLog,
    Ingredient,
    IngredientType,
    Product,
    RecipeItem,
    RecipeModifier,
    SquareUnmappedItem,
    UnitType,
)


class IngredientTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = IngredientType

    name = factory.Sequence(lambda n: f"Type {n}")


class UnitTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UnitType

    name = factory.Sequence(lambda n: f"Unit {n}")
    abbreviation = factory.Sequence(lambda n: f"U{n}")


class IngredientFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Ingredient

    name = factory.Sequence(lambda n: f"Ingredient {n}")
    type = factory.SubFactory(IngredientTypeFactory)
    unit_type = factory.SubFactory(UnitTypeFactory)
    average_cost_per_unit = 1.00
    current_stock = 10
    reorder_point = 5


class ProductFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Product

    name = factory.Sequence(lambda n: f"Product {n}")
    sku = factory.Sequence(lambda n: f"SKU{n:05d}")
    active = True

    @factory.post_generation
    def categories(self, create, extracted, **kwargs):
        if not create or not extracted:
            return
        for category in extracted:
            self.categories.add(category)


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f"Category {n}")


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
    ingredient_type = factory.SubFactory(IngredientTypeFactory)
    behavior = RecipeModifier.ModifierBehavior.ADD
    ingredient = factory.SubFactory(
        IngredientFactory,
        type=factory.SelfAttribute("..ingredient_type"),
    )
    base_quantity = 1
    unit = "oz"
    cost_per_unit = 0
    price_per_unit = 0


class ImportLogFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ImportLog

    source = "square"
    run_type = "live"
    created_at = factory.LazyFunction(timezone.now)
    rows_processed = 10
    matched_count = 8
    unmatched_count = 2
    error_count = 0


class SquareUnmappedItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SquareUnmappedItem

    item_name = factory.Sequence(lambda n: f"Unknown Item {n}")
    price_point_name = "Default"
    normalized_item = factory.LazyAttribute(lambda o: o.item_name.lower())
    normalized_price_point = factory.LazyAttribute(
        lambda o: (o.price_point_name or "").lower()
    )
    last_reason = "not matched"
    seen_count = 1

