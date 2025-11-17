"""
───────────────────────────────────────────────────────────────────────────────
import_chemistry.py
───────────────────────────────────────────────────────────────────────────────
Purpose:
    This management command performs a controlled import of “chemistry” data —
    the authoritative definitions for ingredients and recipe modifiers used
    throughout the MSCR Inventory app.

    It reads a curated CSV file (usually created manually in Numbers or Excel)
    and ensures that all Ingredient and RecipeModifier records are up to date.

    Typical use:
        python manage.py import_chemistry --file path/to/chemistry.csv

Data model alignment:
    - Updates Ingredient.average_cost_per_unit (not cost_per_unit).
    - Retains price_per_unit for future COGS integration.
    - Auto-creates IngredientType and UnitType references as needed.
    - Skips malformed rows and logs every action.

Logging & safety:
    - Each row is processed in an independent savepoint to prevent partial
      transaction failures.
    - Logs all actions (create, update, skip, error) to both console and
      archive/logs/import_chemistry_<timestamp>.log.

CSV columns required:
    type,name,unit_type,base_quantity,size_multiplier,
    cost_per_unit,price_per_unit,modifier_type,create_ingredient,create_modifier

Row customization flags:
    - create_ingredient (defaults to TRUE when omitted) lets a row update or
      skip touching Ingredient records.
    - create_modifier (defaults to TRUE when omitted) lets a row update or
      skip touching RecipeModifier records.

Example rows:
    ingredient,Espresso Beans,oz,1,False,0.45,0.90,BASE,TRUE,TRUE
    ingredient,Holiday Syrup,oz,1,False,0.75,1.10,FLAVOR,FALSE,TRUE
    ingredient,Winter Blend,lb,1,False,18.00,0.00,COFFEE,TRUE,FALSE

Maintainers:
    Use this command when updating your core recipe “chemistry” or ingredient
    cost definitions. It should not be used for daily sync operations (handled
    by import_square_csv.py and sync_orders.py).

───────────────────────────────────────────────────────────────────────────────
"""

import csv
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mscrInventory.models import Ingredient, RecipeModifier, IngredientType, UnitType


class Command(BaseCommand):
    """Import curated chemistry CSV rows for ingredients and modifiers."""
    help = "Batch import ingredients and recipe modifiers from a curated CSV file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file", "-f", required=True, help="Path to the CSV file for import"
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")

        # Logging setup
        log_dir = Path("archive/logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"import_chemistry_{timezone.now():%Y%m%d_%H%M}.log"

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
        )
        logger = logging.getLogger(__name__)
        logger.info("🚀 Starting import_chemistry")

        created_ing = updated_ing = created_mod = updated_mod = skipped = 0

        with open(file_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            expected = [
                "type", "name", "unit_type", "base_quantity", "size_multiplier",
                "cost_per_unit", "price_per_unit", "modifier_type", "create_ingredient", "create_modifier",
            ]
            optional_flags = {"create_ingredient", "create_modifier"}
            missing = [c for c in expected if c not in reader.fieldnames]
            missing_required = [c for c in missing if c not in optional_flags]
            if missing_required:
                raise CommandError(f"Missing required columns: {', '.join(missing_required)}")
            if missing and not missing_required:
                logger.info(
                    "ℹ️ Optional columns absent (%s); defaulting to TRUE for each flag.",
                    ", ".join(sorted(optional_flags.intersection(missing))),
                )

            for row_num, row in enumerate(reader, start=2):
                sid = transaction.savepoint()
                try:
                    # Basic validation
                    row_type = (row.get("type") or "").strip().lower()
                    name = (row.get("name") or "").strip()
                    if not name:
                        logger.warning(f"⏩ Skipped row {row_num}: missing name → {row}")
                        skipped += 1
                        transaction.savepoint_rollback(sid)
                        continue
                    if row_type not in ("ingredient",):
                        logger.warning(f"⏩ Skipped row {row_num}: invalid type '{row_type}' → {row}")
                        skipped += 1
                        transaction.savepoint_rollback(sid)
                        continue

                    # Parse numeric fields safely
                    def safe_decimal(val):
                        try:
                            return Decimal(val or "0")
                        except (InvalidOperation, TypeError):
                            return Decimal("0")

                    base_qty = safe_decimal(row.get("base_quantity"))
                    size_mult = str(row.get("size_multiplier", "")).strip().lower() in ("true", "1", "yes")
                    avg_cost = safe_decimal(row.get("cost_per_unit"))
                    #price = safe_decimal(row.get("price_per_unit"))
                    category_name = (row.get("modifier_type") or "Miscellaneous").strip().title()
                    unit_name = (row.get("unit_type") or "Unit").strip().title()

                    def parse_bool(value, default=True):
                        if value is None or value == "":
                            return default
                        if isinstance(value, bool):
                            return value
                        return str(value).strip().lower() in {"true", "1", "yes", "y"}

                    create_ing = parse_bool(row.get("create_ingredient"), default=True)
                    create_mod = parse_bool(row.get("create_modifier"), default=True)

                    # Ensure category and unit exist
                    category, _ = IngredientType.objects.get_or_create(name=category_name)
                    unit_obj, _ = UnitType.objects.get_or_create(name=unit_name)

                    ing = None
                    if create_ing:
                        # Create or update Ingredient
                        ing, created = Ingredient.objects.get_or_create(
                            name=name,
                            defaults={
                                "unit_type": unit_obj,
                                "average_cost_per_unit": avg_cost,
                                #"price_per_unit": price,
                                "type": category,
                            },
                        )
                        if created:
                            created_ing += 1
                            logger.info(f"✅ Created Ingredient: {name}")
                        else:
                            changed_fields = []
                            if ing.unit_type_id != unit_obj.id:
                                ing.unit_type = unit_obj
                                changed_fields.append("unit_type")
                            if ing.average_cost_per_unit != avg_cost:
                                ing.average_cost_per_unit = avg_cost
                                changed_fields.append("average_cost_per_unit")
                            # if getattr(ing, "price_per_unit", None) != price:
                            #         ing.price_per_unit = price
                            #         changed_fields.append("price_per_unit"),
                            if ing.type_id != category.id:
                                ing.type = category
                                changed_fields.append("type")
                            if changed_fields:
                                ing.save(update_fields=changed_fields)
                                updated_ing += 1
                                logger.info(
                                    f"🔁 Updated Ingredient ({', '.join(changed_fields)}): {name}"
                                )
                    else:
                        logger.info(f"ℹ️ Skipped ingredient creation for {name} (flag false)")
                        ing = Ingredient.objects.filter(name=name).first()

                    if create_mod:
                        if ing is None:
                            logger.error(
                                "❌ Cannot process modifier for %s: ingredient is missing.",
                                name,
                            )
                            skipped += 1
                            transaction.savepoint_rollback(sid)
                            continue

                        # Create or update corresponding RecipeModifier
                        mod, mod_created = RecipeModifier.objects.get_or_create(
                            name=name,
                            defaults={
                                "ingredient": ing,
                                "unit": unit_name,
                                "base_quantity": base_qty,
                                "size_multiplier": size_mult,
                                "cost_per_unit": avg_cost,
                                #"price_per_unit": price,
                                "ingredient_type": category,
                            },
                        )
                        if mod_created:
                            created_mod += 1
                            logger.info(f"✅ Created Modifier: {name}")
                        else:
                            mod_changed = []
                            if mod.ingredient_id != ing.id:
                                mod.ingredient = ing
                                mod_changed.append("ingredient")
                            if mod.unit != unit_name:
                                mod.unit = unit_name
                                mod_changed.append("unit")
                            if mod.base_quantity != base_qty:
                                mod.base_quantity = base_qty
                                mod_changed.append("base_quantity")
                            if mod.size_multiplier != size_mult:
                                mod.size_multiplier = size_mult
                                mod_changed.append("size_multiplier")
                            if mod.cost_per_unit != avg_cost:
                                mod.cost_per_unit = avg_cost
                                mod_changed.append("cost_per_unit")
                            #if mod.price_per_unit != price:
                            #    mod.price_per_unit = price
                            #    mod_changed.append("price_per_unit")
                            if mod.ingredient_type_id != category.id:
                                mod.ingredient_type = category
                                mod_changed.append("ingredient_type")

                            if mod_changed:
                                mod.save(update_fields=mod_changed)
                                updated_mod += 1
                                logger.info(
                                    f"🔁 Updated Modifier ({', '.join(mod_changed)}): {name}"
                                )
                    else:
                        logger.info(f"ℹ️ Skipped modifier creation for {name} (flag false)")

                    transaction.savepoint_commit(sid)

                except Exception as e:
                    transaction.savepoint_rollback(sid)
                    skipped += 1
                    logger.error(f"❌ Error on row {row_num} ({name or 'Unnamed'}): {e}")

        logger.info("────────────────────────────────────────")
        logger.info(
            f"Import complete:\n"
            f"Ingredients created: {created_ing}, updated: {updated_ing}\n"
            f"Modifiers created: {created_mod}, updated: {updated_mod}\n"
            f"Skipped/failed rows: {skipped}\n"
            f"Log saved to: {log_file}"
        )
        logger.info("✅ All done.")
