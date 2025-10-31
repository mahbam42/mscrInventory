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
from mscrInventory.models import (
    Ingredient, Product, RecipeModifier,
    ProductVariantCache, Order, OrderItem
)
from importers._match_product import _find_best_product_match, _normalize_name, _extract_descriptors
from importers._handle_extras import handle_extras, normalize_modifier
from importers._aggregate_usage import resolve_modifier_tree, aggregate_ingredient_usage, infer_temp_and_size

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
        self.buffer = []
        self.stats = {
            "rows_processed": 0,
            "matched": 0,
            "added": 0,
            "modifiers_applied": 0,
            "errors": 0,
        }

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

            # --- Create or update the order (daily batch file as order reference) ---
            order_obj, _ = Order.objects.get_or_create(
                platform="square",
                order_id=file_path.stem if file_path else "test_row",
                defaults={
                    "order_date": datetime.now(),
                    "total_amount": Decimal("0.00"),
                },
            )

            # --- Cache descriptors ---
            if product and descriptors:
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

            # --- Log or persist order items ---
            reference_name = product.name if product else item_name
            temp_type, size = infer_temp_and_size(reference_name, descriptors)

            if product:
                unit = (gross_sales / max(qty, 1)) if qty else Decimal("0.00")
                OrderItem.objects.create(
                    order=order_obj,
                    product=product,
                    quantity=int(qty),
                    unit_price=unit,
                    variant_info={"adjectives": descriptors, "modifiers": normalized_modifiers},
                )
                order_obj.total_amount += gross_sales
                order_obj.save(update_fields=["total_amount"])
                self.stats["added"] += 1

            # 🧩 Apply extras and modifiers (includes descriptors now)
            recipe_map = {
                ri.ingredient.name: {
                    "qty": ri.quantity,
                    "type": ri.ingredient.type.name if ri.ingredient.type else "",
                }
                for ri in product.recipe_items.select_related("ingredient", "ingredient__type").all()
            } if product else {}

            current_recipe_map = recipe_map
            change_logs: list[dict] = []
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

            # --- Aggregate ingredient usage ---
            if product:
                resolved_modifiers = []
                for token in all_modifiers:
                    modifier = RecipeModifier.objects.filter(name__iexact=token).first()
                    if modifier:
                        resolved_modifiers += resolve_modifier_tree(modifier)

                recipe_items = product.recipe_items.select_related("ingredient").all()

                usage_summary = aggregate_ingredient_usage(
                    recipe_items, resolved_modifiers, temp_type=temp_type, size=size
                )

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
                        self.buffer.append(f"   {ing}: {qty} (from {sources})")

            # 🧮 Dry-run log
            if self.dry_run:
                base_name = (product.name if product else item_name) or "(unnamed)"
                display_name = f"{base_name} ({size})" if size else base_name
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
                self._process_row(row, file_path=file_path)

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
#taco