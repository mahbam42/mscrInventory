"""Import historical ingredient rows from a simplified CSV."""

import csv
from decimal import Decimal
from pathlib import Path
from django.core.management.base import BaseCommand
from mscrInventory.models import Ingredient, UnitType, IngredientType

class Command(BaseCommand):
    """Map legacy CSV columns into Ingredient rows."""
    help = "Import ingredients from legacy CSV (text-based unit/type names)."

    def add_arguments(self, parser):
        parser.add_argument("--file", "-f", required=True, help="Path to the legacy CSV file")

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.exists():
            self.stderr.write(f"❌ File not found: {path}")
            return

        created = 0
        updated = 0

        with open(path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row["name"].strip()
                unit_name = row.get("unit_type_name", "").strip()
                type_name = row.get("type_name", "").strip()

                unit = UnitType.objects.filter(name__iexact=unit_name).first()
                if not unit:
                    unit = UnitType.objects.filter(abbreviation__iexact=unit_name).first()
                ing_type = IngredientType.objects.filter(name__iexact=type_name).first()

                if not unit or not ing_type:
                    self.stderr.write(f"⚠️ Skipping {name} — missing unit or type ({unit_name}/{type_name})")
                    continue

                avg_cost = Decimal(row.get("average_cost_per_unit") or "0")
                stock = Decimal(row.get("current_stock") or "0")

                ing, created_flag = Ingredient.objects.update_or_create(
                    name=name,
                    defaults={
                        "unit_type": unit,
                        "type": ing_type,
                        "average_cost_per_unit": avg_cost,
                        "current_stock": stock,
                    },
                )
                if created_flag:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(f"✅ Imported {created} new, updated {updated} existing ingredients.")
