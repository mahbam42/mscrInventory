""" taco 
square_importer.py
------------------
Primary importer for Square CSV data.

Handles:
- CSV reading (via run_from_file)
- Row-level parsing and normalization (process_row)
- Modifier resolution and expansion (handle_extras)
- Safe dry-run and summary reporting

This class is called either from:
  1. Django management command (`import_square.py`)
  2. Web dashboard upload view (`upload_square_view`)
"""

import csv
import re
from io import StringIO
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from django.db import transaction
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from mscrInventory.models import Ingredient, Order, OrderItem, Product, RecipeModifier, ProductVariantCache
from importers._handle_extras import handle_extras, normalize_modifier
from importers._match_product import _find_best_product_match, _normalize_name, _extract_descriptors


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def parse_money(value) -> Decimal:
    """
    Convert Square-style currency strings into Decimal.

    Examples:
        "$3.50" → Decimal("3.50")
        "3.5"   → Decimal("3.50")
        "" or None → Decimal("0.00")
    """
    if not value:
        return Decimal("0.00")
    try:
        clean = str(value).replace("$", "").replace(",", "").strip()
        return Decimal(clean)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")

# ---------------------------------------------------------------------------
# Base Importer
# ---------------------------------------------------------------------------
class SquareImporter:
    """Handles parsing and importing Square CSV exports."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.buffer = []
        self.stats = {
            "rows_processed": 0,
            "matched": 0,
            "added": 0,
            "modifiers_applied": 0,
            "errors": 0,
        }

    # ------------------------------------------------------------------
    # 🧾 Core Importer Logic
    # ------------------------------------------------------------------

    
    @transaction.atomic
    def run_from_file(self, file_path: Path):
        """Run import from a given CSV file."""
        start_time = datetime.now()
        self.buffer.append(f"📥 Importing {file_path.name} ({'dry-run' if self.dry_run else 'live'})")

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                try:
                    self.stats["rows_processed"] += 1

                    item_name = (row.get("item") or "").strip()  # ✅ correct header
                    price_point = (row.get("Price Point Name") or "").strip()
                    modifiers_raw = (row.get("Modifiers Applied") or "").strip()
                    qty = Decimal(row.get("Qty", "1") or "1")
                    gross_sales = Decimal(str(row.get("Gross Sales", "0")).replace("$", "").strip() or "0")

                    # Split and normalize any modifiers that Square provided
                    modifiers = [m.strip() for m in modifiers_raw.split(",") if m.strip()]
                    normalized_modifiers = [normalize_modifier(m) for m in modifiers]

                    # 🧠 Extract descriptors (size/temp adjectives) from item_name
                    normalized_item = _normalize_name(item_name)
                    core_name, descriptors = _extract_descriptors(normalized_item)

                    # Combine descriptors with modifiers for full context
                    all_modifiers = list(set(normalized_modifiers + descriptors))

                    # 🧩 Find best product match (based on core_name only)
                    product, reason = _find_best_product_match(item_name, price_point, normalized_modifiers, buffer=self.buffer)

                    if product:
                        # Cache descriptors as normalized variant
                        if descriptors:
                            variant_name = " ".join(descriptors).strip().lower()
                            cache_entry, created = ProductVariantCache.objects.get_or_create(
                                product=product,
                                platform="square",
                                variant_name=variant_name,
                                defaults={"data": {"adjectives": descriptors}}
                            )
                            if not created:
                                cache_entry.usage_count += 1
                                cache_entry.save(update_fields=["usage_count", "last_seen"])
                            self.buffer.append(f"🧩 Cached variant: {variant_name} ({'new' if created else 'updated'})")

                    # --- Create or update the order (daily batch file as order reference) ---
                    order_obj, _ = Order.objects.get_or_create(
                        platform="square",
                        order_id=file_path.stem,  # use filename like "sales_2025-10-28"
                        defaults={
                            "order_date": datetime.now(),
                            "total_amount": Decimal("0.00"),
                        },
                    )

                    # --- Log or persist order items ---
                    if product:
                        order_item = OrderItem.objects.create(
                            order=order_obj,
                            product=product,
                            quantity=int(qty),
                            unit_price=(gross_sales / max(qty, 1)),
                            variant_info={"adjectives": descriptors, "modifiers": normalized_modifiers},
                        )
                        self.stats["added"] += 1

                    # 🧩 Apply extras and modifiers (includes descriptors now)
                    recipe_map = {
                        ri.ingredient.name: {
                            "qty": ri.quantity,
                            "type": ri.ingredient.type.name if ri.ingredient.type else "",
                        }
                        for ri in product.recipe_items.select_related("ingredient", "ingredient__type").all()
                    } if product else {}

                    for token in all_modifiers:
                        # Verbose only in dry-run mode for clarity
                        result = handle_extras(
                            token,
                            recipe_map,
                            normalized_modifiers,
                            recipe_context=list(recipe_map.keys()),
                            verbose=self.dry_run,
                        )
                        if result:
                            recipe_map.update(result)
                            self.stats["modifiers_applied"] += 1

                    if self.dry_run and recipe_map:
                        self.buffer.append(f"   🧾 Final recipe map: {len(recipe_map)} ingredients")

                    """ # 🧩 Apply extras and modifiers (includes descriptors now)
                    recipe_map = {}
                    for token in all_modifiers:
                        result = handle_extras(token, recipe_map, normalized_modifiers)
                        if result:
                            self.stats["modifiers_applied"] += 1 """

                    # 🧮 Dry-run log
                    if self.dry_run:
                        self.buffer.append(f"→ {item_name} ({price_point}) x{qty} @ {gross_sales}")
                        if descriptors:
                            self.buffer.append(f"   ↳ cached descriptors: {descriptors}")

                except Exception as e:
                    self.stats["errors"] += 1
                    self.buffer.append(f"❌ Error on row {self.stats['rows_processed']}: {e}")
                    continue

        self._summarize(start_time)
        return "\n".join(self.buffer)
    
    # ------------------------------------------------------------------
    # 🔍 Product matching helper
    # ------------------------------------------------------------------

    def _find_best_product_match(self, item_name, price_point, modifiers):
        """
        Find the most appropriate Product for a Square row.

        Match order:
        1. Exact Item Name
        2. Partial Item Name
        3. Combined Item + Price Point
        4. Fallback to products in 'base_item' category
        5. Unmapped (None)
        """
        item_name = (item_name or "").strip()
        price_point = (price_point or "").strip()

        # 1️⃣ Exact Item Name
        product = Product.objects.filter(name__iexact=item_name).first()
        if product:
            return product, "exact"

        # 2️⃣ Partial Item Name
        product = Product.objects.filter(name__icontains=item_name).first()
        if product:
            return product, "partial_item"

        # 3️⃣ Combined Item + Price Point
        combo = f"{item_name} {price_point}".strip()
        if combo and combo != item_name:
            product = Product.objects.filter(name__iexact=combo).first()
            if product:
                return product, "exact_combo"
            product = Product.objects.filter(name__icontains=combo).first()
            if product:
                return product, "partial_combo"

        # 4️⃣ Base-item fallback (category = base_item)
        base_products = Product.objects.filter(categories__name__iexact="base_item")
        product = base_products.filter(name__icontains=item_name).first()
        if product:
            return product, "base_fallback"

        # 5️⃣ Unmapped
        return None, "unmapped"

    # ------------------------------------------------------------------
    # 📊 Summary
    # ------------------------------------------------------------------

    def _summarize(self, start_time):
        elapsed = (datetime.now() - start_time).total_seconds()
        self.buffer.append("")
        self.buffer.append("📊 **Square Import Summary**")
        self.buffer.append(f"Started: {start_time:%Y-%m-%d %H:%M:%S}")
        self.buffer.append(f"Elapsed: {elapsed:.2f}s\n")
        self.buffer.append(f"🧾 Rows processed: {self.stats['rows_processed']}")
        self.buffer.append(f"✅ Products matched: {self.stats['matched']}")
        self.buffer.append(f"➕ New products added: {self.stats['added']}")
        self.buffer.append(f"⚙️ Modifiers applied: {self.stats['modifiers_applied']}")
        self.buffer.append(f"⚠️ Errors: {self.stats['errors']}")
        self.buffer.append("✅ Dry-run complete." if self.dry_run else "✅ Import complete.")