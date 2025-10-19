# scripts/relink_from_backup.py
#!/usr/bin/env python3
"""
Rebuild broken recipe and modifier relationships using backup CSVs.
"""
import os
import sys
import csv
from pathlib import Path

# ---------------------------------------------------------------------
# 🧭 Ensure this script can find Django properly
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

import django
django.setup()

from django.db import transaction
from mscrInventory.models import Product, Ingredient, RecipeItem, RecipeModifier

BACKUP_DIR = Path("archive/backup_CSVs/backup_20251017_203604")

def load_csv(filename):
    path = BACKUP_DIR / filename
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def build_name_lookup(rows, id_field="id", name_field="name"):
    """Map old IDs → names from the backup CSV."""
    lookup = {}
    for r in rows:
        key = str(r[id_field]).strip()
        val = r[name_field].strip()
        if key and val:
            lookup[key] = val
    return lookup

@transaction.atomic
def handle():
    print("🔍 Loading backup CSVs...")
    products_csv = load_csv("mscrInventory_product.csv")
    ingredients_csv = load_csv("mscrInventory_ingredient.csv")
    recipeitems_csv = load_csv("mscrInventory_recipeitem.csv")
    product_mods_csv = load_csv("mscrInventory_product_modifiers.csv")

    product_lookup = build_name_lookup(products_csv)
    ingredient_lookup = build_name_lookup(ingredients_csv)

    repaired_ri, missing_ri = 0, 0
    print("🔧 Repairing RecipeItem relationships...")

    for row in recipeitems_csv:
        old_pid = row["product_id"].strip()
        old_iid = row["ingredient_id"].strip()
        qty = row.get("quantity") or 0
        unit = row.get("unit") or "unit"

        prod_name = product_lookup.get(old_pid)
        ingr_name = ingredient_lookup.get(old_iid)

        if not prod_name or not ingr_name:
            missing_ri += 1
            continue

        product = Product.objects.filter(name__iexact=prod_name).first()
        ingredient = Ingredient.objects.filter(name__iexact=ingr_name).first()

        if product and ingredient:
            ri, created = RecipeItem.objects.get_or_create(
                product=product,
                ingredient=ingredient,
                defaults={"quantity": qty, "unit": unit}
            )
            if not created:
                ri.quantity = qty
                ri.unit = unit
                ri.save(update_fields=["quantity", "unit"])
            repaired_ri += 1
        else:
            missing_ri += 1

    print(f"✅ Repaired {repaired_ri} RecipeItem links ({missing_ri} missing)")

    # -----------------------------------------------------------------
    repaired_pm, missing_pm = 0, 0
    print("🔧 Repairing Product ↔ Modifier links...")

    # Load RecipeModifiers into memory for speed
    all_mods = {m.id: m for m in RecipeModifier.objects.all()}
    for row in product_mods_csv:
        old_pid = row["product_id"].strip()
        old_mid = row["recipemodifier_id"].strip()
        prod_name = product_lookup.get(old_pid)

        product = Product.objects.filter(name__iexact=prod_name).first()
        modifier = all_mods.get(int(old_mid)) if old_mid.isdigit() else None

        if product and modifier:
            product.modifiers.add(modifier)
            repaired_pm += 1
        else:
            missing_pm += 1

    print(f"✅ Repaired {repaired_pm} Product–Modifier links ({missing_pm} missing)")

    print("\n🎉 Relationship repair complete.")

if __name__ == "__main__":
    from django import setup
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
    setup()
    handle()
