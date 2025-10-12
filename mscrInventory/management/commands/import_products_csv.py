import csv
from django.core.management.base import BaseCommand, CommandError
from mscrInventory.models import Product, Category
from django.db import transaction
import re
from django.utils.text import slugify
from uuid import uuid4

def generate_auto_sku(name: str) -> str:
    """
    Generate a stable-ish auto SKU from the name.
    We slugify the name and append a short unique suffix to avoid collisions.
    Example: "B-Stingah Latte" → "ag-b-stingah-latte-3f2a"
    """
    base_slug = slugify(name)[:40]  # keep it manageable
    suffix = uuid4().hex[:4]
    return f"ag-{base_slug}-{suffix}"

class Command(BaseCommand):
    help = "Import products from a CSV file with categories and flags."
    
    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="Path to the CSV file to import")

    @transaction.atomic
    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        try:
            with open(csv_path, newline="", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                count = 0
                for row in reader:
                    # name = row.get("name", "").strip()
                    # sku = row.get("sku", "").strip()
                    # if not name or not sku:
                    #     self.stdout.write(self.style.WARNING(f"⚠️ Skipping row with missing name or sku: {row}"))
                    #     continue
                    name = row.get("name", "").strip()
                    sku = row.get("sku", "").strip() or None
                    if not name:
                        self.stdout.write(self.style.WARNING(f"⚠️ Skipping row with missing name: {row}"))
                        continue

                    # Auto-generate SKU if missing
                    if not sku:
                        sku = generate_auto_sku(name)

                    lookup_kwargs = {"sku": sku}
                    defaults = {
                        "name": name,
                        "temperature_type": row.get("temperature_type", "NA").upper(),
                    }

                    product, created = Product.objects.get_or_create(
                        sku=sku,
                        defaults={
                            "name": name,
                            "temperature_type": row.get("temperature_type", "NA").upper(),
                        }
                    )

                    # Handle categories (multiple separated by '/')
                    categories_str = row.get("categories", "").strip()
                    if categories_str:
                        category_names = [c.strip() for c in categories_str.split("/")]
                        category_objs = []
                        for cname in category_names:
                            cat, _ = Category.objects.get_or_create(name=cname)
                            category_objs.append(cat)
                        product.categories.set(category_objs)

                    # Boolean flags
                    product.is_drink = row.get("is_drink", "").strip().upper() == "TRUE"
                    product.is_food = row.get("is_food", "").strip().upper() == "TRUE"
                    product.is_coffee = row.get("is_coffee", "").strip().upper() == "TRUE"

                    product.save()
                    count += 1

                self.stdout.write(self.style.SUCCESS(f"✅ Imported or updated {count} products successfully."))

        except FileNotFoundError:
            raise CommandError(f"File not found: {csv_path}")
        except Exception as e:
            raise CommandError(f"Error importing products: {e}")
