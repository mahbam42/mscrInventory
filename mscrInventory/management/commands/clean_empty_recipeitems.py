"""Management command to clean up invalid or duplicate RecipeItem rows."""

from django.core.management.base import BaseCommand
from django.db.models import Q, Count
from mscrInventory.models import RecipeItem, Ingredient

class Command(BaseCommand):
    """Remove empty RecipeItems and optionally orphaned Ingredients."""
    help = "Cleans up invalid or duplicate RecipeItems. Use --dry-run to preview actions. \
    Examples: \
    python manage.py clean_empty_recipeitems --dry-run \
    python manage.py clean_empty_recipeitems"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview what would be deleted or merged without applying changes.",
        )
        parser.add_argument(
            "--include-ingredients",
            action="store_true",
            help="Also remove orphaned or blank-named Ingredients.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        include_ingredients = options["include_ingredients"]
        total_deleted = 0
        total_merged = 0

        if dry_run:
            self.stdout.write(self.style.WARNING("⚙️ Running in DRY-RUN mode — no changes will be made.\n"))

        # 1️⃣ Find invalid / empty RecipeItems
        bad_items = (
            RecipeItem.objects.filter(
                Q(product__isnull=True)
                | Q(ingredient__isnull=True)
                | Q(quantity__isnull=True)
                | Q(quantity=0)
                | Q(unit__isnull=True)
                | Q(unit__exact="")
            )
            .distinct()
        )

        # Check for linked ingredients with empty names separately
        bad_by_empty_ingredient = RecipeItem.objects.filter(
            ingredient__in=Ingredient.objects.filter(Q(name__isnull=True) | Q(name__exact=""))
        )

        # Combine both sets safely
        bad_items = bad_items.union(bad_by_empty_ingredient)
        bad_count = bad_items.count()

        if bad_count:
            self.stdout.write(self.style.WARNING(f"🧹 Found {bad_count} invalid or empty RecipeItem(s):"))
            for item in bad_items.select_related("product", "ingredient")[:25]:
                self.stdout.write(
                    f"   - ID {item.id} | product={getattr(item.product, 'name', None)} | "
                    f"ingredient={getattr(item.ingredient, 'name', None)} | qty={item.quantity} | unit='{item.unit}'"
                )
            if bad_count > 25:
                self.stdout.write(f"   ... and {bad_count - 25} more")

            if not dry_run:
                deleted_count, _ = bad_items.delete()
                total_deleted += deleted_count
        else:
            self.stdout.write(self.style.SUCCESS("✅ No invalid RecipeItems found."))

        # 2️⃣ Detect duplicates (same product + ingredient)
        dupes = (
            RecipeItem.objects.values("product_id", "ingredient_id")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )

        if dupes.exists():
            self.stdout.write(self.style.WARNING(f"\n🔍 Found {dupes.count()} duplicate ingredient groups:"))
            for d in dupes:
                product_id = d["product_id"]
                ingredient_id = d["ingredient_id"]
                duplicates = RecipeItem.objects.filter(product_id=product_id, ingredient_id=ingredient_id).order_by("id")

                keeper = duplicates.first()
                others = duplicates.exclude(id=keeper.id)
                total_qty = sum(ri.quantity or 0 for ri in duplicates)

                self.stdout.write(
                    f"   - Product {product_id}, Ingredient {ingredient_id}: "
                    f"{duplicates.count()} entries (merged qty={total_qty})"
                )

                if not dry_run:
                    keeper.quantity = total_qty
                    keeper.save(update_fields=["quantity"])
                    deleted_count = others.count()
                    others.delete()
                    total_deleted += deleted_count
                    total_merged += 1
        else:
            self.stdout.write(self.style.SUCCESS("✅ No duplicate RecipeItems found."))

        # 3️⃣ Optional: Clean up orphaned or blank Ingredients
        if include_ingredients:
            blank_ingredients = Ingredient.objects.filter(Q(name__isnull=True) | Q(name__exact=""))
            orphaned_ingredients = Ingredient.objects.filter(recipeitem__isnull=True)

            blank_count = blank_ingredients.count()
            orphan_count = orphaned_ingredients.count()

            if blank_count or orphan_count:
                self.stdout.write(
                    self.style.WARNING(
                        f"\n🍶 Found {blank_count} blank-named and {orphan_count} orphaned Ingredient(s)."
                    )
                )
                to_delete = blank_ingredients.union(orphaned_ingredients)
                for ing in to_delete[:25]:
                    self.stdout.write(f"   - ID {ing.id} | name='{ing.name}'")
                if not dry_run:
                    deleted_count, _ = to_delete.delete()
                    total_deleted += deleted_count
            else:
                self.stdout.write(self.style.SUCCESS("✅ No orphaned or blank Ingredients found."))

        # ✅ Summary
        summary_msg = (
            f"\n✅ Cleanup complete — deleted {total_deleted} rows, merged {total_merged} duplicate groups."
            if not dry_run
            else f"\n🔎 DRY RUN COMPLETE — would delete {bad_count} invalid RecipeItems and merge {dupes.count()} groups."
        )
        self.stdout.write(self.style.SUCCESS(summary_msg))
