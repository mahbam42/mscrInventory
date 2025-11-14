"""
square_importer.py
------------------
Primary importer for Square CSV data.
Handles:
- CSV reading (via run_from_file)
- Row-level parsing and normalization (via _process_row)
- Modifier resolution and expansion (handle_extras)
- Safe dry-run and summary reporting
"""

import csv
from collections import defaultdict
from contextlib import nullcontext
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import transaction
from django.db.models.functions import Length
from django.utils import timezone

from mscrInventory.models import (
    Ingredient,
    Product,
    RecipeModifier,
    ProductVariantCache,
    Order,
    OrderItem,
    RoastProfile,
    SquareUnmappedItem,
    get_or_create_roast_profile,
)
from importers._match_product import (
    _find_best_product_match,
    _normalize_name,
    _extract_descriptors,
    SIZE_DESCRIPTOR_WORDS,
)
from importers._handle_extras import handle_extras, normalize_modifier
from importers._aggregate_usage import (
    resolve_modifier_tree,
    aggregate_ingredient_usage,
    infer_temp_and_size,
)


def _build_recipe_map_from_product(product: Product | None):
    if not product:
        return {}
    items = product.recipe_items.select_related("ingredient", "ingredient__type").all()
    return {
        ri.ingredient.name: {
            "qty": ri.quantity,
            "type_id": getattr(ri.ingredient.type, "id", None),
            "type_name": ri.ingredient.type.name if ri.ingredient.type else "",
            "type": ri.ingredient.type.name if ri.ingredient.type else "",
        }
        for ri in items
    }


def _find_barista_base_product(product: Product | None) -> Product | None:
    if not product:
        return None

    base_qs = Product.objects.filter(categories__name__iexact="base_item")
    normalized = _normalize_name(product.name)
    tokens = [t for t in normalized.split() if t]

    for start in range(len(tokens)):
        suffix = " ".join(tokens[start:])
        if not suffix:
            continue
        candidate = (
            base_qs.filter(name__icontains=suffix)
            .order_by(Length("name"))
            .first()
        )
        if candidate:
            return candidate

    keywords = [
        "latte",
        "mocha",
        "americano",
        "macchiato",
        "cold brew",
        "coldbrew",
        "nitro",
        "chai",
        "cappuccino",
        "frappe",
        "smoothie",
    ]
    for keyword in keywords:
        if keyword in normalized:
            candidate = (
                base_qs.filter(name__icontains=keyword)
                .order_by(Length("name"))
                .first()
            )
            if candidate:
                return candidate

    return None


def _product_is_drink(product: Product | None) -> bool:
    if not product:
        return False
    category_names = [
        (cat.name or "").lower()
        for cat in product.categories.all()
    ]
    drink_tokens = {
        "barista",
        "coffee",
        "coldbrew",
        "cold brew",
        "espresso",
        "tea",
        "drink",
        "beverage",
        "base",
        "catering",
    }
    for name in category_names:
        for token in drink_tokens:
            if token in name:
                return True
    return False


RETAIL_BAG_NAMES = {"retail bag"}

BAG_SIZE_ALIASES = {
    "3 oz": "3oz",
    "3oz": "3oz",
    "11 oz": "11oz",
    "11oz": "11oz",
    "20 oz": "20oz",
    "20oz": "20oz",
    "5 lb": "5lb",
    "5lb": "5lb",
    "80 oz": "5lb",
    "80oz": "5lb",
}

GRIND_ALIASES = {
    "whole bean": "whole",
    "whole": "whole",
    "drip grind": "drip",
    "drip": "drip",
    "espresso grind": "espresso",
    "espresso": "espresso",
    "coarse grind": "coarse",
    "coarse": "coarse",
    "fine grind": "fine",
    "fine": "fine",
}


def _extract_retail_bag_details(tokens: list[str]) -> tuple[str | None, str | None, str | None]:
    roast_candidates: list[str] = []
    bag_size: str | None = None
    grind: str | None = None

    for raw in tokens:
        token = (raw or "").strip().lower()
        if not token:
            continue

        cleaned = token

        for alias, canonical in BAG_SIZE_ALIASES.items():
            if alias in cleaned:
                if bag_size is None:
                    bag_size = canonical
                cleaned = cleaned.replace(alias, " ")

        for alias, canonical in GRIND_ALIASES.items():
            if alias in token:
                grind = canonical
                cleaned = cleaned.replace(alias, " ")

        cleaned = cleaned.replace("retail bag", " ")
        cleaned = cleaned.replace("bag", " ")
        cleaned = cleaned.replace("coffee", " ")
        cleaned = " ".join(cleaned.split())

        if cleaned:
            roast_candidates.append(cleaned)

    roast_name = None
    if roast_candidates:
        roast_candidates.sort(key=len, reverse=True)
        roast_name = roast_candidates[0]

    return roast_name, bag_size, grind


def _locate_roast_ingredient(roast_name: str | None) -> Ingredient | None:
    if not roast_name:
        return None

    roast_qs = Ingredient.objects.filter(type__name__iexact="roasts")
    candidate = roast_qs.filter(name__iexact=roast_name).first()
    if candidate:
        return candidate

    candidate = roast_qs.filter(name__icontains=roast_name).order_by(Length("name")).first()
    if candidate:
        return candidate

    return Ingredient.objects.filter(name__iexact=roast_name).first()


def _build_recipe_map_from_product(product: Product | None):
    if not product:
        return {}
    items = product.recipe_items.select_related("ingredient", "ingredient__type").all()
    return {
        ri.ingredient.name: {
            "qty": ri.quantity,
            "type_id": getattr(ri.ingredient.type, "id", None),
            "type_name": ri.ingredient.type.name if ri.ingredient.type else "",
            "type": ri.ingredient.type.name if ri.ingredient.type else "",
        }
        for ri in items
    }


def _find_barista_base_product(product: Product | None) -> Product | None:
    if not product:
        return None

    base_qs = Product.objects.filter(categories__name__iexact="base_item")
    normalized = _normalize_name(product.name)
    tokens = [t for t in normalized.split() if t]

    for start in range(len(tokens)):
        suffix = " ".join(tokens[start:])
        if not suffix:
            continue
        candidate = (
            base_qs.filter(name__icontains=suffix)
            .order_by(Length("name"))
            .first()
        )
        if candidate:
            return candidate

    keywords = [
        "latte",
        "mocha",
        "americano",
        "macchiato",
        "cold brew",
        "coldbrew",
        "nitro",
        "chai",
        "cappuccino",
        "frappe",
        "smoothie",
    ]
    for keyword in keywords:
        if keyword in normalized:
            candidate = (
                base_qs.filter(name__icontains=keyword)
                .order_by(Length("name"))
                .first()
            )
            if candidate:
                return candidate

    return None

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def parse_money(value) -> Decimal:
    """Convert Square-style currency strings into Decimal."""
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
        self.buffer: list[str] = []
        self.stats = {
            "rows_processed": 0,
            "matched": 0,
            "unmatched": 0,
            "order_items_logged": 0,
            "modifiers_applied": 0,
            "errors": 0,
        }
        self._summary_added = False
        self._summary_cache: list[str] | None = None
        self._last_run_started: datetime | None = None
        self._last_run_finished: datetime | None = None
        self._current_order: Order | None = None
        self._orders_by_transaction: dict[str, Order | None] = {}
        self._unmapped_seen_keys: set[tuple[str, str]] = set()
        self.usage_totals: defaultdict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        self.usage_breakdown: defaultdict[int, defaultdict[str, Decimal]] = defaultdict(
            lambda: defaultdict(lambda: Decimal("0"))
        )
        self._ingredient_cache: dict[str, Ingredient | None] = {}

    # ------------------------------------------------------------------
    # 🧩 Single-row processing
    # ------------------------------------------------------------------
    def _resolve_ingredient(self, name: str | None) -> Ingredient | None:
        normalized = (name or "").strip().lower()
        if not normalized:
            return None
        if normalized in self._ingredient_cache:
            return self._ingredient_cache[normalized]
        ingredient = Ingredient.objects.filter(name__iexact=name).first()
        self._ingredient_cache[normalized] = ingredient
        return ingredient

    def _record_usage_totals(
        self,
        *,
        product: Product | None,
        fallback_name: str,
        descriptors: list[str],
        price_point: str,
        usage_summary: dict,
        quantity: Decimal,
    ) -> None:
        if not usage_summary or quantity <= 0:
            return

        base_label = (product.name if product else fallback_name) or "(unknown)"
        descriptor_bits = [bit for bit in descriptors if bit]
        label_base = base_label
        if descriptor_bits:
            label_base = f"{base_label} ({' '.join(descriptor_bits)})"
        elif price_point:
            label_base = f"{base_label} [{price_point}]"

        for ingredient_name, data in usage_summary.items():
            ingredient = self._resolve_ingredient(ingredient_name)
            if not ingredient:
                continue
            raw_qty = data.get("qty", Decimal("0"))
            try:
                per_unit_qty = Decimal(raw_qty)
            except (InvalidOperation, TypeError, ValueError):
                continue
            ingredient_qty = per_unit_qty * quantity
            if ingredient_qty <= 0:
                continue

            metadata_bits = [
                str(bit)
                for bit in (data.get("bag_size"), data.get("grind"))
                if bit
            ]
            entry_label = label_base
            if metadata_bits:
                entry_label = f"{label_base} [{' | '.join(metadata_bits)}]"

            self.usage_totals[ingredient.id] += ingredient_qty
            self.usage_breakdown[ingredient.id][entry_label] += ingredient_qty

    def _parse_order_datetime(self, row: dict) -> datetime | None:
        """Parse a Square CSV row into a timezone-aware datetime."""

        date_raw = (row.get("Date") or "").strip()
        time_raw = (row.get("Time") or "").strip()

        if not date_raw:
            return None

        candidate_strings: list[str] = []

        if time_raw:
            candidate_strings.append(f"{date_raw} {time_raw}")
            candidate_strings.append(f"{date_raw}T{time_raw}")
        candidate_strings.append(date_raw)

        formats = [
            "%m/%d/%Y %I:%M:%S %p",
            "%m/%d/%Y %I:%M %p",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%m/%d/%y %I:%M:%S %p",
            "%m/%d/%y %I:%M %p",
            "%m/%d/%y %H:%M:%S",
            "%m/%d/%y %H:%M",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%m/%d/%y",
        ]

        for candidate in candidate_strings:
            for fmt in formats:
                try:
                    parsed = datetime.strptime(candidate, fmt)
                except ValueError:
                    continue

                tz = timezone.get_current_timezone()
                if timezone.is_naive(parsed):
                    try:
                        parsed = timezone.make_aware(parsed, tz)
                    except Exception:  # pragma: no cover - fallback safety
                        parsed = parsed.replace(tzinfo=tz)
                return parsed

        return None

    def _process_row(self, row: dict, file_path: Path | None = None):
        """Parse and process a single CSV row."""
        change_logs = []
        try:
            self.stats["rows_processed"] += 1

            item_name = (row.get("Item") or "").strip()
            price_point = (row.get("Price Point Name") or "").strip()
            modifiers_raw = (row.get("Modifiers Applied") or "").strip()
            qty_raw = row.get("Qty", "1") or "1"
            try:
                qty = Decimal(qty_raw)
            except (InvalidOperation, TypeError, ValueError):
                qty = Decimal("0")
            gross_sales = Decimal(str(row.get("Gross Sales", "0")).replace("$", "").strip() or "0")
            event_type = (
                row.get("Event Type")
                or row.get("Event type")
                or row.get("Event_Type")
                or ""
            ).strip()
            event_type_normalized = event_type.lower()
            is_voided_item = "(voided)" in item_name.lower()

            # --- Collect modifiers (Square-provided or price-point) ---
            modifiers = [m.strip() for m in modifiers_raw.split(",") if m.strip()]

            # Include price_point as a modifier if not already present
            if price_point and price_point.lower() not in [m.lower() for m in modifiers]:
                modifiers.append(price_point.strip())

            # Normalize all modifiers *after* adding price_point
            normalized_modifiers = [normalize_modifier(m) for m in modifiers]

            # --- Extract descriptors (size/temp adjectives) ---
            normalized_item = _normalize_name(item_name)
            normalized_price = _normalize_name(price_point)
            core_name, item_descriptors = _extract_descriptors(normalized_item)
            _, price_descriptors = _extract_descriptors(normalized_price)

            descriptors = list(item_descriptors)
            for token in price_descriptors:
                if token and token not in descriptors:
                    descriptors.append(token)

            descriptor_tokens = list(descriptors)
            for token in normalized_modifiers:
                if token and token not in descriptor_tokens:
                    descriptor_tokens.append(token)

            modifier_descriptor_tokens: list[str] = []
            for token in normalized_modifiers:
                _, token_descriptors = _extract_descriptors(token)
                for desc in token_descriptors:
                    if desc and desc not in modifier_descriptor_tokens:
                        modifier_descriptor_tokens.append(desc)

            if not any(t in SIZE_DESCRIPTOR_WORDS for t in modifier_descriptor_tokens):
                for token in item_descriptors:
                    if (
                        token in SIZE_DESCRIPTOR_WORDS
                        and token not in modifier_descriptor_tokens
                    ):
                        modifier_descriptor_tokens.append(token)

            for token in price_descriptors:
                if token and token not in modifier_descriptor_tokens:
                    modifier_descriptor_tokens.append(token)

            # Combine modifiers + derived size/temp tokens (preserve order)
            seen = set()
            all_modifiers = []
            combined_tokens = normalized_modifiers + modifier_descriptor_tokens
            for token in combined_tokens:
                if token and token not in seen:
                    seen.add(token)
                    all_modifiers.append(token)

            # Shows consistent context, even if the match fails or an exception occurs
            self.buffer.append(f"\nRow {self.stats['rows_processed']}:")
            self.buffer.append(f"  🏷 Item: {item_name}")
            self.buffer.append(f"  💲 Price Point: {price_point or '(none)'}")
            modifier_display = ", ".join(normalized_modifiers) if normalized_modifiers else "(none)"
            self.buffer.append(f"  🔧 Modifiers: {modifier_display}")
            if event_type:
                self.buffer.append(f"  🛈 Event Type: {event_type}")

            if is_voided_item:
                self.buffer.append("  ⚠️ Skipping row because the item was voided.")
                return

            if qty <= 0:
                self.buffer.append(f"  ⚠️ Skipping row due to non-positive quantity ({qty}).")
                return

            if "refund" in event_type_normalized:
                self.buffer.append("  ⚠️ Skipping row because it is a refund event.")
                return

            # 🧩 Find best product match (based on core_name only)
            resolved_mapping = (
                SquareUnmappedItem.objects.filter(
                    source="square",
                    item_type="product",
                    normalized_item=normalized_item,
                    normalized_price_point=normalized_price,
                    resolved=True,
                    ignored=False,
                )
                .select_related("linked_product")
                .first()
            )

            if resolved_mapping and resolved_mapping.linked_product:
                product = resolved_mapping.linked_product
                reason = "saved mapping"
                resolved_mapping.last_seen = timezone.now()
                resolved_mapping.save(update_fields=["last_seen"])
                self.buffer.append(
                    f"🔁 Used saved mapping → {product.name}"
                )
            else:
                product, reason = _find_best_product_match(
                    item_name, price_point, normalized_modifiers, buffer=self.buffer
                )

            if product:
                self.stats["matched"] += 1
                self.buffer.append(f"✅ Matched → {product.name} ({reason})")
            else:
                self.stats["unmatched"] += 1
                self._record_unmapped_item(
                    item_name,
                    price_point,
                    normalized_modifiers,
                    reason,
                )
                if reason == "variant_unmapped" and price_point:
                    self.buffer.append(
                        f"⚠️ Variant '{price_point}' not mapped for base item '{item_name}'."
                    )

            transaction_id = self._extract_transaction_id(row, file_path)
            order_dt = self._parse_order_datetime(row)
            order_obj = None
            if self.dry_run:
                display_id = transaction_id or (file_path.stem if file_path else "test_row")
                if display_id not in self._orders_by_transaction:
                    self._orders_by_transaction[display_id] = None
                    self.buffer.append(
                        f"🧪 Would ensure order square#{display_id} exists"
                    )
            else:
                order_obj = self._ensure_order_for_transaction(
                    transaction_id,
                    file_path,
                    order_dt=order_dt,
                )
                self._current_order = order_obj

            # --- Cache descriptors ---
            if product and descriptors:
                variant_name = " ".join(descriptors).strip().lower()
                if self.dry_run:
                    self.buffer.append(
                        f"🧩 Would cache variant: {variant_name}"
                    )
                else:
                    cache_entry, created = ProductVariantCache.objects.get_or_create(
                        product=product,
                        platform="square",
                        variant_name=variant_name,
                        defaults={"data": {"adjectives": descriptors}},
                    )
                    if not created:
                        cache_entry.usage_count += 1
                        cache_entry.save(update_fields=["usage_count", "last_seen"])
                    self.buffer.append(
                        f"🧩 Cached variant: {variant_name} ({'new' if created else 'updated'})"
                    )

            # --- Log or persist order items ---
            reference_name = product.name if product else item_name
            temp_type, size = infer_temp_and_size(reference_name, descriptor_tokens)

            if product:
                unit = (gross_sales / max(qty, 1)) if qty else Decimal("0.00")
                if not self.dry_run and order_obj is not None:
                    OrderItem.objects.create(
                        order=order_obj,
                        product=product,
                        quantity=int(qty),
                        unit_price=unit,
                        variant_info={
                            "adjectives": descriptors,
                            "modifiers": normalized_modifiers,
                        },
                    )
                    order_obj.total_amount += gross_sales
                    order_obj.save(update_fields=["total_amount"])
                self.stats["order_items_logged"] += 1

            # 🧩 Apply extras and modifiers (includes descriptors now)
            change_logs: list[dict] = []
            recipe_map = {}
            base_recipe_product = product
            product_is_drink = _product_is_drink(product)
            base_product_is_drink = False

            if product:
                is_barista_choice = product.categories.filter(name__icontains="barista").exists()
                if is_barista_choice:
                    base_product = _find_barista_base_product(product)
                    if base_product:
                        base_recipe_product = base_product
                        base_product_is_drink = _product_is_drink(base_product)
                        base_map = _build_recipe_map_from_product(base_product)
                        recipe_map, barista_log = handle_extras(
                            product.name,
                            base_map,
                            normalized_modifiers,
                            recipe_context=list(base_map.keys()),
                            verbose=self.dry_run,
                        )
                        if not recipe_map:
                            recipe_map = base_map
                        if barista_log:
                            change_logs.append(barista_log)
                            behavior = barista_log.get("behavior")
                            if behavior not in (None, "ignored_variant"):
                                self.stats["modifiers_applied"] += 1
                    else:
                        recipe_map = _build_recipe_map_from_product(product)
                        base_product_is_drink = product_is_drink
                else:
                    recipe_map = _build_recipe_map_from_product(product)
                    base_product_is_drink = product_is_drink

            current_recipe_map = recipe_map
            for token in all_modifiers:
                context_keys = list(current_recipe_map.keys())
                result, change_log = handle_extras(
                    token,
                    current_recipe_map,
                    normalized_modifiers,
                    recipe_context=context_keys,
                    verbose=self.dry_run,
                )

                if change_log:
                    change_logs.append(change_log)

                if isinstance(result, dict):
                    current_recipe_map = result
                    behavior = change_log.get("behavior") if change_log else None
                    if behavior not in (None, "ignored_variant"):
                        self.stats["modifiers_applied"] += 1

            final_recipe_map = current_recipe_map
            is_drink_context = product_is_drink or base_product_is_drink

            # --- Aggregate ingredient usage ---
            usage_summary: dict[str, dict] = {}
            if product:
                resolved_modifiers = []
                for token in all_modifiers:
                    modifier = RecipeModifier.objects.filter(name__iexact=token).first()
                    if modifier:
                        resolved_modifiers += resolve_modifier_tree(modifier)

                recipe_source = base_recipe_product if base_recipe_product else product
                recipe_items = recipe_source.recipe_items.select_related("ingredient").all()

                usage_summary = aggregate_ingredient_usage(
                    recipe_items,
                    resolved_modifiers,
                    temp_type=temp_type,
                    size=size,
                    overrides_map=final_recipe_map,
                    is_drink=is_drink_context,
                    modifier_tokens=all_modifiers,
                )

                is_retail_bag = False
                if product and (product.name or ""):
                    is_retail_bag = product.name.strip().lower() in RETAIL_BAG_NAMES

                if is_retail_bag:
                    roast_name, bag_size, grind_label = _extract_retail_bag_details(normalized_modifiers)
                    roast_ingredient = _locate_roast_ingredient(roast_name)

                    if roast_ingredient:
                        profile = None
                        profile_updates: list[str] = []

                        if self.dry_run:
                            try:
                                profile = roast_ingredient.roastprofile
                            except RoastProfile.DoesNotExist:
                                profile = None
                                self.buffer.append(
                                    f"🧪 Would create roast profile for {roast_ingredient.name}"
                                )
                        else:
                            profile = get_or_create_roast_profile(roast_ingredient)

                        if profile:
                            if bag_size and getattr(profile, "bag_size", None) != bag_size:
                                if self.dry_run:
                                    profile_updates.append("bag_size")
                                else:
                                    profile.bag_size = bag_size
                                    profile_updates.append("bag_size")
                            if grind_label and getattr(profile, "grind", None) != grind_label:
                                if self.dry_run:
                                    profile_updates.append("grind")
                                else:
                                    profile.grind = grind_label
                                    profile_updates.append("grind")

                            if profile_updates:
                                if self.dry_run:
                                    updates = ", ".join(profile_updates)
                                    self.buffer.append(
                                        f"🧪 Would update roast profile {roast_ingredient.name}: {updates}"
                                    )
                                else:
                                    profile.save(update_fields=profile_updates)

                        usage_summary = {
                            roast_ingredient.name: {
                                "qty": qty,
                                "sources": ["retail_bag"],
                                "unit_type": "unit",
                                "bag_size": bag_size or getattr(profile, "bag_size", None),
                                "grind": grind_label or getattr(profile, "grind", None),
                            }
                        }
                    else:
                        if self.dry_run and roast_name:
                            self.buffer.append(f"⚠️  No roast ingredient found for '{roast_name}'")

                replacements: list[tuple[str, str]] = []
                additions: dict[str, set[str]] = {}
                for log in change_logs:
                    replaced_entries = [
                        tuple(entry)
                        for entry in log.get("replaced", [])
                        if isinstance(entry, (list, tuple)) and len(entry) == 2
                    ]
                    replacements.extend(replaced_entries)

                    behavior_label = log.get("behavior")
                    if behavior_label is None:
                        behavior_str = "modifier_add"
                    elif hasattr(behavior_label, "value"):
                        behavior_str = behavior_label.value
                    else:
                        behavior_str = str(behavior_label)

                    for name in log.get("added", []):
                        additions.setdefault(name, set()).add(behavior_str)

                for old, new in replacements:
                    if old in usage_summary:
                        moved = usage_summary.pop(old)
                        moved["sources"].append("renamed_from_modifier")
                        usage_summary[new] = moved

                for name, behaviors in additions.items():
                    if name in usage_summary:
                        existing_sources = set(usage_summary[name].get("sources", []))
                        for source in behaviors:
                            if source not in existing_sources:
                                usage_summary[name]["sources"].append(source)
                    elif name in final_recipe_map:
                        meta = final_recipe_map.get(name, {})
                        qty = meta.get("qty", Decimal("0.00"))
                        usage_summary[name] = {
                            "qty": qty,
                            "sources": sorted(behaviors),
                        }

                if self.dry_run:
                    self.buffer.append("\n🧾 Final ingredient usage:")
                    for ing, data in usage_summary.items():
                        qty = data["qty"]
                        sources = ", ".join(data["sources"])
                        metadata_bits = [bit for bit in [data.get("bag_size"), data.get("grind")] if bit]
                        if metadata_bits:
                            meta_str = " | ".join(metadata_bits)
                            self.buffer.append(f"   {ing}: {qty} (from {sources}) [{meta_str}]")
                        else:
                            self.buffer.append(f"   {ing}: {qty} (from {sources})")

                self._record_usage_totals(
                    product=product,
                    fallback_name=item_name,
                    descriptors=list(descriptors),
                    price_point=price_point,
                    usage_summary=usage_summary,
                    quantity=qty,
                )

            # 🧮 Dry-run log
            if self.dry_run:
                base_name = (product.name if product else item_name) or "(unnamed)"
                if is_drink_context and size:
                    display_name = f"{base_name} ({size})"
                else:
                    display_name = base_name
                self.buffer.append(f"→ {display_name} x{qty} @ {gross_sales}")
                if descriptors:
                    variant_name = " ".join(descriptors)
                    self.buffer.append(f"   🧩 Variant detected: {variant_name}")
                if normalized_modifiers:
                    self.buffer.append(f"   🔧 Modifiers normalized: {normalized_modifiers}")
                            
        except Exception as e:
            self.stats["errors"] += 1
            self.buffer.append(f"❌ Error on row {self.stats['rows_processed']}: {e}")
            return self.buffer

        return self.buffer

    def _extract_transaction_id(self, row: dict, file_path: Path | None) -> str:
        candidates = [
            "Transaction ID",
            "Transaction Id",
            "Transaction Id(s)",
            "Transaction",
            "Transaction UUID",
            "Payment ID",
            "Payment Id",
            "Payment ID(s)",
        ]
        for key in candidates:
            raw = row.get(key)
            if raw:
                value = str(raw).strip()
                if value:
                    return value
        return file_path.stem if file_path else "square-order"

    def _ensure_order_for_transaction(
        self,
        transaction_id: str,
        file_path: Path | None,
        order_dt: datetime | None = None,
    ) -> Order:
        key = transaction_id or (file_path.stem if file_path else "square-order")
        if key in self._orders_by_transaction:
            existing_order = self._orders_by_transaction[key]
            if existing_order and order_dt:
                current_dt = existing_order.order_date
                if current_dt is None or order_dt < current_dt:
                    existing_order.order_date = order_dt
                    existing_order.save(update_fields=["order_date"])
            return existing_order

        order_date = order_dt or timezone.now()
        order_obj, created = Order.objects.get_or_create(
            platform="square",
            order_id=key,
            defaults={
                "order_date": order_date,
                "total_amount": Decimal("0.00"),
            },
        )
        if not created:
            order_obj.items.all().delete()

        updated_fields = ["total_amount"]

        if created:
            order_obj.order_date = order_date
        elif order_dt:
            current_dt = order_obj.order_date
            effective_dt = order_dt
            if current_dt is None or effective_dt < current_dt:
                order_obj.order_date = effective_dt
                updated_fields.append("order_date")

        order_obj.total_amount = Decimal("0.00")
        order_obj.save(update_fields=updated_fields)
        self._orders_by_transaction[key] = order_obj
        action = "created" if created else "reset"
        self.buffer.append(f"🧾 Using order square#{key} ({action})")
        return order_obj

    # ------------------------------------------------------------------
    # 🧾 Batch importer wrapper
    # ------------------------------------------------------------------
    def run_from_file(self, file_path: Path):
        """Run import from a given CSV file."""
        self.buffer = []
        self.stats = {
            "rows_processed": 0,
            "matched": 0,
            "unmatched": 0,
            "order_items_logged": 0,
            "modifiers_applied": 0,
            "errors": 0,
        }
        self.usage_totals = defaultdict(lambda: Decimal("0"))
        self.usage_breakdown = defaultdict(lambda: defaultdict(lambda: Decimal("0")))
        self._ingredient_cache = {}
        start_time = timezone.now()
        self._last_run_started = start_time
        self._summary_added = False
        self._summary_cache = None
        self._unmapped_seen_keys = set()
        self._orders_by_transaction = {}
        self.buffer.append(
            f"📥 Importing {file_path.name} ({'dry-run' if self.dry_run else 'live'})"
        )

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        context = nullcontext() if self.dry_run else transaction.atomic()

        with context:
            if not self.dry_run:
                self._current_order = None
            with open(file_path, newline="", encoding="utf-8-sig") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    self._process_row(row, file_path=file_path)

            self.summarize()

            if self.dry_run:
                self._current_order = None

        self._last_run_finished = timezone.now()
        self._current_order = None
        return self.get_output()

    # ------------------------------------------------------------------
    # 📊 Summary
    # ------------------------------------------------------------------
    def summarize(self):
        if self._summary_added and self._summary_cache is not None:
            return "\n".join(self._summary_cache)

        start_time = self._last_run_started or timezone.now()
        end_time = self._last_run_finished or timezone.now()
        elapsed = (end_time - start_time).total_seconds()

        summary_lines = [
            "",
            "📊 Square Import Summary",
            f"Started: {start_time:%Y-%m-%d %H:%M:%S}",
            f"Elapsed: {elapsed:.2f}s",
            "",
            f"🧾 Rows processed: {self.stats['rows_processed']}",
            f"✅ Products matched: {self.stats['matched']}",
            f"⚠️ Unmatched items: {self.stats['unmatched']}",
            f"🧺 Order items logged: {self.stats['order_items_logged']}",
            f"🧩 Modifiers applied: {self.stats['modifiers_applied']}",
            f"❌ Errors: {self.stats['errors']}",
            "✅ Dry-run complete." if self.dry_run else "✅ Import complete.",
        ]

        self.buffer.extend(summary_lines)
        self._summary_added = True
        self._summary_cache = summary_lines
        return "\n".join(summary_lines)

    def get_run_metadata(self) -> dict:
        """Return structured metadata about the most recent run."""
        stats = dict(self.stats)
        started_at = self._last_run_started
        finished_at = self._last_run_finished
        duration = None
        if started_at and finished_at:
            duration = (finished_at - started_at).total_seconds()

        return {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_seconds": duration,
            "stats": stats,
        }

    def get_output(self) -> str:
        """Return the collected log as a single string."""
        return "\n".join(self.buffer)

    def get_summary(self) -> str:
        """Return the formatted summary for display (without mutating twice)."""
        return self.summarize()

    def get_usage_totals(self) -> dict[int, Decimal]:
        return {
            ingredient_id: qty
            for ingredient_id, qty in self.usage_totals.items()
            if qty > 0
        }

    def get_usage_breakdown(self) -> dict[str, dict[str, Decimal]]:
        result: dict[str, dict[str, Decimal]] = {}
        for ingredient_id, per_source in self.usage_breakdown.items():
            ingredient = Ingredient.objects.filter(id=ingredient_id).first()
            name = ingredient.name if ingredient else f"Ingredient #{ingredient_id}"
            result[name] = dict(per_source)
        return result

    # ------------------------------------------------------------------
    # ⚠️ Unmapped tracking helpers
    # ------------------------------------------------------------------
    def _record_unmapped_item(self, item_name, price_point, modifiers, reason) -> None:
        normalized_item = _normalize_name(item_name)
        normalized_price = _normalize_name(price_point)
        key = (normalized_item, normalized_price)
        seen_in_run = key in self._unmapped_seen_keys
        self._unmapped_seen_keys.add(key)

        now = timezone.now()
        defaults = {
            "source": "square",
            "item_type": "product",
            "item_name": item_name or "(unknown)",
            "price_point_name": price_point or "",
            "normalized_item": normalized_item,
            "normalized_price_point": normalized_price,
            "last_modifiers": modifiers,
            "last_reason": reason or "unmapped",
            "seen_count": 1,
            "first_seen": now,
            "last_seen": now,
        }

        obj, created = SquareUnmappedItem.objects.get_or_create(
            normalized_item=normalized_item,
            normalized_price_point=normalized_price,
            defaults=defaults,
        )

        if created:
            label = "🧪" if self.dry_run else "⚠️"
            self.buffer.append(
                f"{label} No product match found; recorded as unmapped (first seen {now:%Y-%m-%d %H:%M})."
            )
            return

        updates = {"last_seen": now}
        if item_name and item_name != obj.item_name:
            updates["item_name"] = item_name
        if price_point and price_point != obj.price_point_name:
            updates["price_point_name"] = price_point
        if not seen_in_run:
            updates["seen_count"] = obj.seen_count + 1
        updates["last_modifiers"] = modifiers
        if reason and reason != obj.last_reason:
            updates["last_reason"] = reason

        reopened = False
        if obj.resolved and not obj.ignored:
            has_link = any(
                [
                    obj.linked_product_id,
                    obj.linked_ingredient_id,
                    obj.linked_modifier_id,
                ]
            )
            if not has_link:
                obj.reopen()
                reopened = True

        if reopened:
            updates["resolved"] = obj.resolved
            updates["ignored"] = obj.ignored
            updates["resolved_at"] = obj.resolved_at
            updates["resolved_by"] = obj.resolved_by

        for field, value in updates.items():
            setattr(obj, field, value)

        update_fields = list(updates.keys())
        if "item_name" in update_fields and "normalized_item" not in update_fields:
            update_fields.append("normalized_item")
        if "price_point_name" in update_fields and "normalized_price_point" not in update_fields:
            update_fields.append("normalized_price_point")

        obj.save(update_fields=update_fields)

        first_seen = obj.first_seen.strftime("%Y-%m-%d %H:%M")
        base_message = (
            f"No product match found; first recorded {first_seen} (seen {obj.seen_count}×)."
        )
        if seen_in_run:
            base_message = (
                f"Still unmapped (first recorded {first_seen}; seen {obj.seen_count}×)."
            )
        label = "🧪" if self.dry_run else "⚠️"
        self.buffer.append(f"{label} {base_message}")
