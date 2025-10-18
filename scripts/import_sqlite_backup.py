import csv
import os
import django
import logging
from django.db import IntegrityError, transaction

# --- Django setup ---
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mscrInventory.settings")
django.setup()

from mscrInventory import models  # noqa: E402

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("import_log.txt"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# --- Config ---
DATA_DIR = os.path.join("scripts", "sqlite_backup")
SKIP_ON_ERROR = True  # Change to False if you want to stop on first error


def import_csv(model, filename, required_fields=None):
    """Import CSV rows into the given model with validation and logging."""
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        logger.warning(f"⚠️ File not found: {path}")
        return 0, 0, 0

    created, skipped, errors = 0, 0, 0
    required_fields = required_fields or []

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Trim whitespace and normalize blanks
            row = {k: (v.strip() or None) for k, v in row.items()}

            # Validate required fields
            if any(not row.get(field) for field in required_fields):
                skipped += 1
                logger.warning(f"⏩ Skipping invalid row in {filename}: {row}")
                continue

            try:
                with transaction.atomic():
                    model.objects.create(**row)
                    created += 1
            except IntegrityError as e:
                errors += 1
                logger.warning(f"❌ Skipped row in {filename}: {e}")
                if not SKIP_ON_ERROR:
                    raise
            except Exception as e:
                errors += 1
                logger.error(f"💥 Unexpected error in {filename}: {e}")
                if not SKIP_ON_ERROR:
                    raise

    logger.info(f"✅ Imported {created} rows from {filename} "
                f"(skipped {skipped}, errors {errors})")
    return created, skipped, errors


def main():
    logger.info("🚀 Starting SQLite CSV import...")
    total_created = total_skipped = total_errors = 0

    # --- Define import order (respecting FK dependencies) ---
    IMPORT_ORDER = [
        # filename, model, required_fields
        ("mscrInventory_category.csv", models.Category, ["name"]),
        ("mscrInventory_ingredient.csv", models.Ingredient, ["name"]),
        ("mscrInventory_product.csv", models.Product, ["name"]),
        ("mscrInventory_recipe.csv", models.Recipe, ["name"]),
        ("mscrInventory_recipeitem.csv", models.RecipeItem, ["recipe_id", "ingredient_id"]),
        ("mscrInventory_product_categories.csv", models.ProductCategory, ["product_id", "category_id"]),
        ("mscrInventory_product_modifiers.csv", models.ProductModifier, ["product_id", "modifier_id"]),
        ("mscrInventory_recipemodifier.csv", models.RecipeModifier, ["recipe_id", "modifier_id"]),
        ("mscrInventory_recipemodifier_expands_to.csv", models.RecipeModifierExpandsTo, ["recipemodifier_id", "recipeitem_id"]),
    ]

    for filename, model, required_fields in IMPORT_ORDER:
        created, skipped, errors = import_csv(model, filename, required_fields)
        total_created += created
        total_skipped += skipped
        total_errors += errors

    logger.info("🎯 Import complete!")
    logger.info(f"Total created: {total_created}")
    logger.info(f"Total skipped: {total_skipped}")
    logger.info(f"Total errors: {total_errors}")


if __name__ == "__main__":
    main()
