import csv
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mscrInventory.models import Ingredient, RecipeModifier

class Command(BaseCommand):
    help = "Batch import ingredients and modifiers from CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file", "-f", required=True, help="Path to the CSV file for import"
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")

        created_ing = 0
        updated_ing = 0
        created_mod = 0
        updated_mod = 0

        with open(file_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            expected = ["type", "name", "unit_type", "base_quantity",
                        "size_multiplier", "cost_per_unit", "price_per_unit", "modifier_type"]
            for col in expected:
                if col not in reader.fieldnames:
                    self.stderr.write(f"Missing column: {col}")
                    return

            for row in reader:
                row_type = row["type"].strip().lower()
                name = row["name"].strip()
                unit_type = row["unit_type"].strip()
                cost = Decimal(row["cost_per_unit"] or "0")
                price = Decimal(row["price_per_unit"] or "0")

                if row_type == "ingredient":
                    ing, created = Ingredient.objects.get_or_create(
                        name=name,
                        defaults={
                            "unit_type": unit_type,
                            "current_stock": 0,
                            "average_cost_per_unit": cost,
                        },
                    )
                    if created:
                        created_ing += 1
                    else:
                        # option to update cost or unit_type
                        changed = False
                        if ing.unit_type != unit_type:
                            ing.unit_type = unit_type
                            changed = True
                        if ing.average_cost_per_unit != cost:
                            ing.average_cost_per_unit = cost
                            changed = True
                        if changed:
                            ing.save(update_fields=["unit_type", "average_cost_per_unit"])
                            updated_ing += 1

                elif row_type == "modifier":
                    # must exist ingredient first
                    try:
                        ing = Ingredient.objects.get(name=name)
                    except Ingredient.DoesNotExist:
                        self.stderr.write(f"Ingredient for modifier '{name}' not found — skipping modifier.")
                        continue

                    base_qty = Decimal(row["base_quantity"] or "0")
                    size_mult = row["size_multiplier"].strip().lower() in ("true", "1", "yes")
                    mod_type = row["modifier_type"].strip().upper()

                    mod, created = RecipeModifier.objects.get_or_create(
                        name=name,
                        defaults={
                            "ingredient": ing,
                            "unit": unit_type,
                            "base_quantity": base_qty,
                            "size_multiplier": size_mult,
                            "cost_per_unit": cost,
                            "price_per_unit": price,
                            "type": mod_type,
                        },
                    )
                    if created:
                        created_mod += 1
                    else:
                        changed = False
                        # update fields if mismatch
                        fields_to_update = []
                        if mod.ingredient_id != ing.id:
                            mod.ingredient = ing
                            fields_to_update.append("ingredient")
                        if mod.unit != unit_type:
                            mod.unit = unit_type
                            fields_to_update.append("unit")
                        if mod.base_quantity != base_qty:
                            mod.base_quantity = base_qty
                            fields_to_update.append("base_quantity")
                        if mod.size_multiplier != size_mult:
                            mod.size_multiplier = size_mult
                            fields_to_update.append("size_multiplier")
                        if mod.cost_per_unit != cost:
                            mod.cost_per_unit = cost
                            fields_to_update.append("cost_per_unit")
                        if mod.price_per_unit != price:
                            mod.price_per_unit = price
                            fields_to_update.append("price_per_unit")
                        if mod.type != mod_type:
                            mod.type = mod_type
                            fields_to_update.append("type")

                        if fields_to_update:
                            mod.save(update_fields=fields_to_update)
                            updated_mod += 1
                else:
                    self.stderr.write(f"Unknown type '{row_type}' for row: {row}")

        self.stdout.write(self.style.SUCCESS(
            f"Ingredients created: {created_ing}, updated: {updated_ing}\n"
            f"Modifiers created: {created_mod}, updated: {updated_mod}"
        ))
