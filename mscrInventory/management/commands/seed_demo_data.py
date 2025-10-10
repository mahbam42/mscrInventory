# mscrInventory/management/commands/seed_demo_data.py
from __future__ import annotations
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone

from mscrInventory.models import (
    Ingredient, StockEntry, Product, RecipeItem
)

class Command(BaseCommand):
    help = "Seed demo ingredients, stock, products, and recipes."

    def handle(self, *args, **opts):
        # Ingredients
        beans, _ = Ingredient.objects.get_or_create(
            name="House Blend Beans", defaults=dict(unit_type="lb", reorder_point=Decimal("5.000"))
        )
        milk, _ = Ingredient.objects.get_or_create(
            name="Whole Milk", defaults=dict(unit_type="fl_oz", reorder_point=Decimal("256.000"))
        )
        cups, _ = Ingredient.objects.get_or_create(
            name="12oz Cups", defaults=dict(unit_type="unit", case_size=500, reorder_point=Decimal("200.000"))
        )

        # Stock entries (gives us average costs + current stock)
        StockEntry.objects.get_or_create(
            ingredient=beans,
            quantity_added=Decimal("80.000"),
            cost_per_unit=Decimal("4.000"),
            date_received=timezone.now(),
            source="purchase",
            note="2 x 40lb bags"
        )
        StockEntry.objects.get_or_create(
            ingredient=milk,
            quantity_added=Decimal("640.000"),  # ~5 gallons
            cost_per_unit=Decimal("0.020"),     # $0.02 per fl_oz
            date_received=timezone.now(),
            source="purchase"
        )
        StockEntry.objects.get_or_create(
            ingredient=cups,
            quantity_added=Decimal("1000.000"),
            cost_per_unit=Decimal("0.050"),     # 5 cents per cup
            date_received=timezone.now(),
            source="purchase"
        )

        # Products
        latte, _ = Product.objects.get_or_create(name="Latte 12oz", sku="LATTE-12", defaults={"category":"Beverage"})
        beans_bag, _ = Product.objects.get_or_create(name="Beans 12oz Bag", sku="BEANS-12", defaults={"category":"Whole Bean"})

        # Recipes (how much of each ingredient per product)
        RecipeItem.objects.get_or_create(product=latte, ingredient=milk, quantity_per_unit=Decimal("12.000"))
        RecipeItem.objects.get_or_create(product=latte, ingredient=cups, quantity_per_unit=Decimal("1.000"))
        # Assume 12oz bag consumes 0.75 lb roasted beans from inventory
        RecipeItem.objects.get_or_create(product=beans_bag, ingredient=beans, quantity_per_unit=Decimal("0.750"))

        self.stdout.write(self.style.SUCCESS("Demo data seeded."))
