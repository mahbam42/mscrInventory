import os
import sys
import csv
import django
import warnings
import traceback
from pathlib import Path
from datetime import datetime
from django.db import transaction, IntegrityError

# ───────────────────────────────────────────────────────────────
# Django setup
ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from mscrInventory import models  # noqa: E402
from mscrInventory.models import IngredientType, UnitType, Category

# Suppress warnings about naive datetimes
warnings.filterwarnings("ignore", message="DateTimeField.*received a naive datetime")

# ───────────────────────────────────────────────────────────────
# Configuration
BACKUP_DIR = Path("archive/backup_CSVs")
LATEST = (
    Path(sys.argv[1])
    if len(sys.argv) > 1 and not sys.argv[1].startswith("--")
    else sorted(BACKUP_DIR.glob("backup_*"))[-1] if BACKUP_DIR.exists() else None
)
DRY_RUN = "--dry-run" in sys.argv
LOG_FILE = Path("archive") / f"import_log_{datetime.now():%Y%m%d_%H%M}.txt"

TABLE_ORDER = [
    "mscrInventory_unittype",
    "mscrInventory_ingredienttype",
    "mscrInventory_category",
    "mscrInventory_ingredient",
    "mscrInventory_product",
    "mscrInventory_product_categories",
    "mscrInventory_product_modifiers",
    "mscrInventory_recipeitem",
    "mscrInventory_recipemodifier",
    "mscrInventory_recipemodifier_expands_to",
    "mscrInventory_stockentry",
    "mscrInventory_importlog",
    "mscrInventory_ingredientusagelog",
    "mscrInventory_order",
    "mscrInventory_orderitem",
]

MODEL_MAP = {
    "mscrInventory_unittype": models.UnitType,
    "mscrInventory_ingredienttype": models.IngredientType,
    "mscrInventory_category": models.Category,
    "mscrInventory_ingredient": models.Ingredient,
    "mscrInventory_product": models.Product,
    "mscrInventory_product_categories": models.Product.categories.through,
    "mscrInventory_product_modifiers": models.Product.modifiers.through,
    "mscrInventory_recipeitem": models.RecipeItem,
    "mscrInventory_recipemodifier": models.RecipeModifier,
    "mscrInventory_recipemodifier_expands_to": models.RecipeModifier.expands_to.through,
    "mscrInventory_stockentry": models.StockEntry,
    "mscrInventory_importlog": models.ImportLog,
    "mscrInventory_ingredientusagelog": models.IngredientUsageLog,
    "mscrInventory_order": models.Order,
    "mscrInventory_orderitem": models.OrderItem,
}

# ───────────────────────────────────────────────────────────────
def log(message: str):
    print(message)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(message + "\n")


def load_csv(csv_path: Path):
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def clean_value(value):
    if value == "":
        return None
    return value


def import_csv(model, csv_path: Path):
    data = load_csv(csv_path)
    if not data:
        log(f"⚠️  Skipping empty file: {csv_path.name}")
        return 0

    model_fields = {f.name for f in model._meta.get_fields()}
    count = 0
    failed_rows = 0

    for row in data:
        # Skip rows missing mandatory FKs (pre-validation)
        if "product_id" in row and not row["product_id"]:
            log(f"⏩ Skipping invalid FK row in {csv_path.name}: missing product_id")
            continue
        if "category_id" in row and not row["category_id"]:
            log(f"⏩ Skipping invalid FK row in {csv_path.name}: missing category_id")
            continue

        sid = transaction.savepoint()
        try:
            cleaned = {}
            for k, v in row.items():
                if k not in model_fields:
                    continue
                if v == "":
                    if k in ("case_size", "cost_per_case", "cost_per_unit", "price_per_unit"):
                        cleaned[k] = 0
                    else:
                        cleaned[k] = None
                else:
                    cleaned[k] = v

            # Special handling
            if model.__name__ == "Category":
                cleaned["description"] = cleaned.get("description") or ""

            elif model.__name__ == "Ingredient":
                if cleaned.get("type"):
                    cleaned["type"] = IngredientType.objects.get_or_create(name=cleaned["type"])[0]
                if cleaned.get("unit_type"):
                    cleaned["unit_type"] = UnitType.objects.get_or_create(name=cleaned["unit_type"])[0]

            # Drop ID for auto PK
            if not cleaned.get("id"):
                cleaned.pop("id", None)

            if DRY_RUN:
                log(f"🧪 Would import {model.__name__}: {cleaned}")
                transaction.savepoint_rollback(sid)
                continue

            model.objects.create(**cleaned)
            transaction.savepoint_commit(sid)
            count += 1

        except Exception as e:
            failed_rows += 1
            transaction.savepoint_rollback(sid)
            log(f"    ⚠️ Skipped row in {csv_path.name}: {e}")
            continue

    if failed_rows:
        log(f"⚠️  {failed_rows} rows skipped due to errors.")
    return count


# ───────────────────────────────────────────────────────────────
def run_import():
    if not LATEST:
        log("❌ No backup folder found.")
        return

    log(f"📥 Starting import from {LATEST}")
    if DRY_RUN:
        log("🧪 DRY-RUN mode: no data will be written.\n")

    successes, failures = [], []

    base_tables = [
        "mscrInventory_unittype",
        "mscrInventory_ingredienttype",
        "mscrInventory_category",
        "mscrInventory_ingredient",
        "mscrInventory_product",
    ]
    dependent_tables = [t for t in TABLE_ORDER if t not in base_tables]

    for phase, tables in [("Phase 1", base_tables), ("Phase 2", dependent_tables)]:
        log(f"\n🔹 {phase} import")
        for table in tables:
            csv_path = LATEST / f"{table}.csv"
            if not csv_path.exists():
                continue

            model = MODEL_MAP.get(table)
            if not model:
                log(f"→ Importing {table} ... ⚠️  No matching model found.")
                failures.append((table, "No matching model"))
                continue

            try:
                log(f"→ Importing {table} ...")
                count = import_csv(model, csv_path)
                log(f"✅  {count} rows imported")
                successes.append((table, count))
            except IntegrityError:
                log(f"❌  {table}: FOREIGN KEY constraint failed")
                failures.append((table, "FK constraint"))
            except Exception as e:
                log(f"❌  {table}: {e}")
                failures.append((table, str(e)))

    # Summary
    log("\n📊 Import Summary\n" + "─" * 40)
    for table, count in successes:
        log(f"✅ {table}: {count} rows imported")
    if failures:
        log("\n⚠️  Failures:")
        for table, reason in failures:
            log(f"   • {table}: {reason}")
    log(f"\n🧾 Detailed log saved to: {LOG_FILE.absolute()}")


# ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run_import()
