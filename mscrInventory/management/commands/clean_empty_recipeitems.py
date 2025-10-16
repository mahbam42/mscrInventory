from django.core.management.base import BaseCommand
from django.db.models import Q, Count
from mscrInventory.models import RecipeItem

class Command(BaseCommand):
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

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        total_deleted = 0
        total_merged = 0

        if dry_run:
            self.stdout.write(self.style.WARNING("⚙️ Running in DRY-RUN mode — no changes will be made.\n"))

        # 1️⃣ Find invalid / empty RecipeItems
        bad_items = RecipeItem.objects.filter(
            Q(product__isnull=True)
            | Q(ingredient__isnull=True)
            | Q(quantity__isnull=True)
            | Q(quantity=0)
            | Q(unit__isnull=True)
            | Q(unit__exact="")
        )

        bad_count = bad_items.count()
        if bad_count:
            self.stdout.write(self.style.WARNING(f"🧹 Found {bad_count} invalid or empty RecipeItem(s):"))
            for item in bad_items[:20]:
                self.stdout.write(
                    f"   - ID {item.id} | product={getattr(item.product, 'name', None)} | "
                    f"ingredient={getattr(item.ingredient, 'name', None)} | qty={item.quantity} | unit='{item.unit}'"
                )
            if bad_count > 20:
                self.stdout.write(f"   ... and {bad_count - 20} more")
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
                total_qty = sum(ri.quantity for ri in duplicates if ri.quantity)

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

        # ✅ Summary
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"\n🔎 DRY RUN COMPLETE — would delete {bad_count} invalid rows and merge {dupes.count()} duplicate groups."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\n✅ Cleanup complete — deleted {total_deleted} invalid rows, merged {total_merged} duplicate groups."
                )
            )
