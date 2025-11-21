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

from difflib import SequenceMatcher
import re

from django.db.models.functions import Length

from mscrInventory.models import Product

SIZE_DESCRIPTOR_WORDS = ["small", "medium", "large", "xl", "extra", "regular"]
TEMP_DESCRIPTOR_WORDS = ["iced", "hot"]


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
    tokens = name.split()

    descriptors = [
        t for t in tokens if t in SIZE_DESCRIPTOR_WORDS + TEMP_DESCRIPTOR_WORDS
    ]
    core_tokens = [t for t in tokens if t not in descriptors]
    core_name = " ".join(core_tokens).strip()

    return core_name or name, descriptors


GENERIC_MENU_PREFIXES = {
    "baristas choice",
    "barista s choice",
    "barista choice",
    "build your own",
    "custom drink",
}


def _match_variant_by_name(name: str):
    """Attempt to resolve a product directly from a variant/price-point token."""
    normalized = _normalize_name(name)
    if not normalized:
        return None, "variant_unmapped"

    product = (
        Product.objects.filter(name__iexact=name)
        .order_by(Length("name"))
        .first()
    )
    if product:
        return product, "variant_exact"

    product = (
        Product.objects.filter(name__iexact=normalized)
        .order_by(Length("name"))
        .first()
    )
    if product:
        return product, "variant_exact_normalized"

    product = (
        Product.objects.filter(name__icontains=normalized)
        .order_by(Length("name"))
        .first()
    )
    if product:
        return product, "variant_partial"

    return None, "variant_unmapped"


def _find_best_product_match(item_name, price_point, modifiers, buffer=None):
    """Improved product matching logic that preserves descriptors."""
    raw_name = (item_name or "").strip()
    normalized = _normalize_name(raw_name)
    core_name, descriptors = _extract_descriptors(normalized)
    price_point = (price_point or "").strip().lower()
    allowed_descriptor_tokens = set(SIZE_DESCRIPTOR_WORDS + TEMP_DESCRIPTOR_WORDS)
    fuzzy_conflict = False

    def log(msg):
        if buffer is not None:
            # buffer.append(f"[DEBUG] {msg}")  # uncomment to enable debug logging
            pass

    if not core_name:
        log(f"Empty item_name after normalization → '{raw_name}'")
        return None, "empty_name"

    # Detect generic menu containers (e.g. "Barista's Choice") that should rely on
    # the price point / variant name instead of the generic item label.
    normalized_plain = normalized.replace("'", "")
    for prefix in GENERIC_MENU_PREFIXES:
        if normalized_plain.startswith(prefix):
            if price_point:
                variant_product, variant_reason = _match_variant_by_name(price_point)
                if variant_product:
                    log(
                        f"Generic menu item '{raw_name}' resolved via price point '{price_point}'"
                    )
                    return variant_product, variant_reason
            log(
                f"Generic menu item '{raw_name}' without known variant → unmapped"
            )
            return None, "variant_unmapped"

    # 1️⃣ Exact Item Name
    # Try exact match against the raw name first (preserves casing/punctuation)
    product = (
        Product.objects.filter(name__iexact=raw_name)
        .order_by(Length("name"))
        .first()
    )
    if product:
        log(f"Exact match for '{raw_name}'")
        return product, "exact"

    product = (
        Product.objects.filter(name__iexact=_normalize_name(item_name))
        .order_by(Length("name"))
        .first()
    )
    if product:
        log(f"Exact match for '{core_name}' ({descriptors})")
        return product, "exact"

    # 2️⃣ Fuzzy match
    if not product:
        candidates = list(Product.objects.all())
        scored = []
        for c in candidates:
            ratio = SequenceMatcher(None, normalized, _normalize_name(c.name)).ratio()
            if ratio > 0.7:
                scored.append((c, ratio))
        fuzzy_conflict = False
        if scored:
            scored.sort(key=lambda x: x[1], reverse=True)
            item_tokens = normalized.split()

            for candidate, score in scored:
                candidate_tokens = _normalize_name(candidate.name).split()
                extra_tokens = [
                    t for t in candidate_tokens
                    if t not in item_tokens and t not in allowed_descriptor_tokens
                ]
                missing_tokens = [
                    t for t in item_tokens
                    if t not in candidate_tokens and t not in allowed_descriptor_tokens
                ]

                if extra_tokens and missing_tokens:
                    fuzzy_conflict = True
                    log(
                        f"Fuzzy candidate '{candidate.name}' skipped (missing={missing_tokens}, extra={extra_tokens})"
                    )
                    continue

                product = candidate
                log(f"Fuzzy matched → '{product.name}' ({descriptors}) [score={score:.2f}]")

                # 🧩 NEW sanity check: prefer base_item fallback if fuzzy match isn't a base product
                if hasattr(product, "categories"):
                    category_names = [c.name.lower() for c in product.categories.all()]
                    # Check if there exists a base_item with same core_name
                    base_products = Product.objects.filter(
                        categories__name__iexact="base_item",
                        name__icontains=core_name
                    )
                    if base_products.exists() and not any("base_item" in c for c in category_names):
                        base_product = min(base_products, key=lambda p: len(p.name))
                        log(f"Fuzzy match '{product.name}' overridden → base fallback '{base_product.name}'")
                        return base_product, "base_fallback"

                # Otherwise, keep fuzzy result
                return product, "fuzzy_match"


    # 3️⃣ Combined Item + Price Point (for baked goods / variant names)
    combo = f"{core_name} {price_point}".strip()
    if price_point and combo and combo != core_name and price_point.lower() not in {"none", "nan", ""}:
        combo_normalized = _normalize_name(combo)
        product = (
            Product.objects.filter(name__iexact=combo_normalized)
            .order_by(Length("name"))
            .first()
        )
        if product:
            log(f"Exact combo match '{combo}' ({descriptors})")
            return product, "exact_combo"

        # partial match for items like "Bagel Everything" or "Muffin Blueberry"
        product = (
            Product.objects.filter(name__icontains=combo_normalized)
            .order_by(Length("name"))
            .first()
        )
        if product:
            log(f"Partial combo match '{combo}' ({descriptors})")
            return product, "partial_combo"

    # 4️⃣ Base-item fallback (category = base_item)
    base_products = Product.objects.filter(categories__name__iexact="base_item")
    base_matches = list(base_products.filter(name__icontains=core_name))

    if base_matches:
        product = min(base_matches, key=lambda p: len(_normalize_name(p.name)))
        log(f"Base fallback → '{product.name}' ({descriptors})")
        return product, "base_fallback"

    # 5️⃣ General partial fallback – pick the most specific name containing the core token
    if core_name:
        general_matches = list(Product.objects.filter(name__icontains=core_name))
        if general_matches:
            product = min(general_matches, key=lambda p: len(_normalize_name(p.name)))
            log(f"Partial core fallback → '{product.name}' ({descriptors})")
            return product, "partial_core"

    # 5️⃣ Unmapped
    log(f"No match for '{core_name}' ({descriptors})")
    return None, "fuzzy_conflict" if fuzzy_conflict else "unmapped"
