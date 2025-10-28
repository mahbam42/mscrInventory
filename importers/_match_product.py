# importers/_match_product.py
"""
_match_product.py
------------------
Product matching helper for Square CSV importer.

Attempts to find the most appropriate Product instance given:
  - item_name (from Square "Item Name")
  - price_point (from "Price Point Name")
  - modifiers (normalized modifier tokens)

Matching hierarchy:
  1. Exact item name
  2. Partial item name
  3. Exact / partial combo of item + price point
  4. Fallback to 'base_item' category, preferring shortest match
  5. None → "unmapped"

Returns:
  (Product | None, reason_code)
"""

import re
from mscrInventory.models import Product


def _normalize_name(name: str) -> str:
    """Basic cleanup: lowercase, remove punctuation, and normalize spaces."""
    if not name:
        return ""
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9\s]", " ", name)  # remove punctuation
    name = re.sub(r"\s+", " ", name).strip()
    return name


def _extract_descriptors(name: str):
    """
    Identify adjectives like 'iced', 'hot', 'small', 'medium', 'large', etc.
    Returns (core_name, descriptors)
    Example:
        'Iced Small Latte' → ('latte', ['iced', 'small'])
    """
    size_words = ["small", "medium", "large", "xl", "extra", "regular"]
    temp_words = ["iced", "hot"]
    tokens = name.split()

    descriptors = [t for t in tokens if t in size_words + temp_words]
    core_tokens = [t for t in tokens if t not in descriptors]
    core_name = " ".join(core_tokens).strip()

    return core_name or name, descriptors


def _find_best_product_match(item_name, price_point, modifiers, buffer=None):
    """Improved product matching logic that preserves descriptors."""
    raw_name = (item_name or "").strip()
    normalized = _normalize_name(raw_name)
    core_name, descriptors = _extract_descriptors(normalized)
    price_point = (price_point or "").strip().lower()

    def log(msg):
        if buffer is not None:
            # buffer.append(f"[DEBUG] {msg}")  # uncomment to enable debug logging
            pass

    if not core_name:
        log(f"Empty item_name after normalization → '{raw_name}'")
        return None, "empty_name"

    # 1️⃣ Exact Item Name
    product = Product.objects.filter(name__iexact=_normalize_name(item_name)).first()
    if product:
        log(f"Exact match for '{core_name}' ({descriptors})")
        return product, "exact"

    # 2️⃣ Partial Item Name
    product = Product.objects.filter(name__icontains=_normalize_name(core_name)).first()
    if product:
        log(f"Partial match for '{core_name}' ({descriptors})")
        return product, "partial_item"

    # 3️⃣ Combined Item + Price Point
    combo = f"{core_name} {price_point}".strip()
    if combo and combo != core_name:
        product = Product.objects.filter(name__iexact=_normalize_name(combo)).first()
        if product:
            log(f"Exact combo match '{combo}' ({descriptors})")
            return product, "exact_combo"
        product = Product.objects.filter(name__icontains=combo).first()
        if product:
            log(f"Partial combo match '{combo}' ({descriptors})")
            return product, "partial_combo"

    # 4️⃣ Base-item fallback (category = base_item)
    base_products = Product.objects.filter(categories__name__iexact="base_item")
    base_matches = list(base_products.filter(name__icontains=core_name))

    if base_matches:
        product = min(base_matches, key=lambda p: len(p.name))
        log(f"Base fallback → '{product.name}' ({descriptors})")
        return product, "base_fallback"

    # 5️⃣ Unmapped
    log(f"No match for '{core_name}' ({descriptors})")
    return None, "unmapped"