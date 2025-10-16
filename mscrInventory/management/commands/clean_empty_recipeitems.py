from django.core.management.base import BaseCommand
from django.db.models import Count
from mscrInventory.models import RecipeItem

class Command(BaseCommand):
    help = "Cleans RecipeItems with missing data or duplicates. Deletes orphans and merges duplicates safely."

    def handle(self, *args, **options):
        total_deleted = 0
        total_merged = 0

        # 1️⃣ Remove orphaned RecipeItems
        bad_items = RecipeItem.objects.filter(product__isnull=True) | RecipeItem.objects.filter(ingredient__isnull=True)
        bad_count = bad_items.count()

        if bad_count:
            self.stdout.write(self.style.WARNING(f"🧹 Removing {bad_count} orphaned RecipeItem(s)..."))
            total_deleted += bad_count
            bad_items.delete()
        else:
            self.stdout.write(self.style.SUCCESS("✅ No orphaned RecipeItems found."))

        # 2️⃣ Detect duplicates by (product_id, ingredient_id)
        dupes = (
            RecipeItem.objects.values("product_id", "ingredient_id")
            .annotate(count=Count("id"))
            .filter(count__gt=1)
        )

        if dupes.exists():
            self.stdout.write(self.style.WARNING(f"🔍 Found {dupes.count()} duplicate ingredient entries."))

            for d in dupes:
                product_id = d["product_id"]
                ingredient_id = d["ingredient_id"]
                duplicates = RecipeItem.objects.filter(product_id=product_id, ingredient_id=ingredient_id).order_by("id")

                # Keep the first, merge quantities, delete extras
                keeper = duplicates.first()
                others = duplicates.exclude(id=keeper.id)
                total_qty = sum([ri.quantity for ri in duplicates])

                keeper.quantity = total_qty
                keeper.save(update_fields=["quantity"])

                deleted_count = others.count()
                others.delete()

                self.stdout.write(
                    f"🧩 Merged {deleted_count} duplicate(s) for product {product_id}, ingredient {ingredient_id}. "
                    f"New total quantity: {keeper.quantity}"
                )

                total_deleted += deleted_count
                total_merged += 1
        else:
            self.stdout.write(self.style.SUCCESS("✅ No duplicate RecipeItems found."))

        self.stdout.write(self.style.SUCCESS(
            f"\n✅ Cleanup complete. Deleted {total_deleted} invalid entries, merged {total_merged} duplicate groups."
        ))
