"""
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
from mscrInventory.models import Ingredient, Product, RecipeModifier
from importers._handle_extras import handle_extras, normalize_modifier

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
                    item_name = (row.get("Item Name") or "").strip()
                    price_point = (row.get("Price Point Name") or "").strip()
                    modifiers_raw = (row.get("Modifiers Applied") or "").strip()
                    qty = Decimal(row.get("Qty", "1") or "1")
                    gross_sales = Decimal(str(row.get("Gross Sales", "0")).replace("$", "").strip() or "0")

                    modifiers = [m.strip() for m in modifiers_raw.split(",") if m.strip()]
                    normalized = [normalize_modifier(m) for m in modifiers]

                    product, reason = self._find_best_product_match(item_name, price_point, normalized)

                    if product:
                        self.stats["matched"] += 1
                        self.buffer.append(f"✅ Matched product: {product.name} ({reason})")
                    else:
                        self.buffer.append("⚠️ No product match found (unmapped)")

                    recipe_map = {}
                    for token in normalized:
                        result = handle_extras(token, recipe_map, normalized)
                        if result:
                            self.stats["modifiers_applied"] += 1

                    if self.dry_run:
                        self.buffer.append(f"→ {item_name} ({price_point}) x{qty} @ {gross_sales}")

                except Exception as e:
                    self.stats["errors"] += 1
                    self.buffer.append(f"❌ Error on row {self.stats['rows_processed']}: {e}")
                    continue

        self._summarize(start_time)
        return "\n".join(self.buffer)

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