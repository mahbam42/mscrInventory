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
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.db import transaction
from django.db.models.functions import Length

from mscrInventory.models import (
    Ingredient,
    Product,
    RecipeModifier,
    ProductVariantCache,
    Order,
    OrderItem,
    RoastProfile,
    get_or_create_roast_profile,
)
from importers._match_product import _find_best_product_match, _normalize_name, _extract_descriptors
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

    # ------------------------------------------------------------------
    # 🧩 Single-row processing
    # ------------------------------------------------------------------
    def _process_row(self, row: dict, file_path: Path | None = None):
        """Parse and process a single CSV row."""
        change_logs = []
        try:
            self.stats["rows_processed"] += 1

            item_name = (row.get("Item") or "").strip()
            price_point = (row.get("Price Point Name") or "").strip()
            modifiers_raw = (row.get("Modifiers Applied") or "").strip()
            qty = Decimal(row.get("Qty", "1") or "1")
            gross_sales = Decimal(str(row.get("Gross Sales", "0")).replace("$", "").strip() or "0")

            # --- Collect modifiers (Square-provided or price-point) ---
            modifiers = [m.strip() for m in modifiers_raw.split(",") if m.strip()]

            # Include price_point as a modifier if not already present
            if price_point and price_point.lower() not in [m.lower() for m in modifiers]:
                modifiers.append(price_point.strip())

            # Normalize all modifiers *after* adding price_point
            normalized_modifiers = [normalize_modifier(m) for m in modifiers]

            # --- Extract descriptors (size/temp adjectives) ---
            normalized_item = _normalize_name(item_name)
            core_name, descriptors = _extract_descriptors(normalized_item)
            descriptor_tokens = list(descriptors)
            for token in normalized_modifiers:
                if token and token not in descriptor_tokens:
                    descriptor_tokens.append(token)

            # Combine modifiers + descriptors (preserve order while de-duping)
            seen = set()
            all_modifiers = []
            for token in normalized_modifiers + descriptors:
                if token not in seen:
                    seen.add(token)
                    all_modifiers.append(token)

            # Shows consistent context, even if the match fails or an exception occurs
            self.buffer.append(f"\nRow {self.stats['rows_processed']}:")
            self.buffer.append(f"  🏷 Item: {item_name}")
            self.buffer.append(f"  💲 Price Point: {price_point or '(none)'}")
            self.buffer.append(f"  🔧 Modifiers: {normalized_modifiers or '(none)'}")

            # 🧩 Find best product match (based on core_name only)
            product, reason = _find_best_product_match(
                item_name, price_point, normalized_modifiers, buffer=self.buffer
            )

            if product:
                self.stats["matched"] += 1
                self.buffer.append(f"✅ Matched → {product.name} ({reason})")
            else:
                self.stats["unmatched"] += 1
                self.buffer.append("⚠️ No product match found; left unmapped.")

            # --- Create or update the order (daily batch file as order reference) ---
            order_obj = None
            if not self.dry_run:
                order_obj, _ = Order.objects.get_or_create(
                    platform="square",
                    order_id=file_path.stem if file_path else "test_row",
                    defaults={
                        "order_date": datetime.now(),
                        "total_amount": Decimal("0.00"),
                    },
                )
            else:
                display_id = file_path.stem if file_path else "test_row"
                self.buffer.append(
                    f"🧪 Would ensure order square#{display_id} exists"
                )

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

    # ------------------------------------------------------------------
    # 🧾 Batch importer wrapper
    # ------------------------------------------------------------------
    def run_from_file(self, file_path: Path):
        """Run import from a given CSV file."""
        self.buffer = []
        start_time = datetime.now()
        self._last_run_started = start_time
        self._summary_added = False
        self._summary_cache = None
        self.buffer.append(f"📥 Importing {file_path.name} ({'dry-run' if self.dry_run else 'live'})")

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        with transaction.atomic():
            with open(file_path, newline="", encoding="utf-8-sig") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    self._process_row(row, file_path=file_path)

            self.summarize()

            if self.dry_run:
                transaction.set_rollback(True)

        return self.get_output()

    # ------------------------------------------------------------------
    # 📊 Summary
    # ------------------------------------------------------------------
    def summarize(self):
        if self._summary_added and self._summary_cache is not None:
            return "\n".join(self._summary_cache)

        start_time = self._last_run_started or datetime.now()
        elapsed = (datetime.now() - start_time).total_seconds()

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

    def get_output(self) -> str:
        """Return the collected log as a single string."""
        return "\n".join(self.buffer)

    def get_summary(self) -> str:
        """Return the formatted summary for display (without mutating twice)."""
        return self.summarize()
