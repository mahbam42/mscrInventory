"""
Quick dry-run test for _find_best_product_match()
-------------------------------------------------
Run with:
    python manage.py shell < scripts/test_square_matcher.py
or just copy/paste into Django shell.
"""

import csv
from pathlib import Path
from decimal import Decimal
from importers._match_product import _find_best_product_match
from importers._handle_extras import normalize_modifier

# Path to your small test file
TEST_FILE = Path("squareCSVs/squareCSV_importTest1.csv")

buffer = []

print(f"📥 Testing Square matcher with {TEST_FILE.name}\n")

with open(TEST_FILE, newline="", encoding="utf-8-sig") as csvfile:
    reader = csv.DictReader(csvfile)
    for row_num, row in enumerate(reader, start=1):
        item_name = (row.get("Item") or "").strip()
        price_point = (row.get("Price Point Name") or "").strip()
        modifiers_raw = (row.get("Modifiers Applied") or "").strip()

        modifiers = [m.strip() for m in modifiers_raw.split(",") if m.strip()]
        normalized = [normalize_modifier(m) for m in modifiers]

        product, reason = _find_best_product_match(
            item_name, price_point, normalized, buffer=buffer
        )

        print(f"Row {row_num}:")
        print(f"  🏷 Item: {item_name}")
        print(f"  💲 Price Point: {price_point}")
        print(f"  🔧 Modifiers: {modifiers}")
        if product:
            print(f"  ✅ Matched → {product.name} ({reason})\n")
        else:
            print(f"  ⚠️  No match ({reason})\n")

# Optional: dump debug logs
print("\n".join(buffer))
