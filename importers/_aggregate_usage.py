"""
_aggregate_usage.py
-------------------
Ingredient usage aggregation with size/temperature scaling.

This version:
- Scales recipes based on inferred size + temperature
- Rounds generously (½ oz for liquids, whole units for discrete)
- Prepares for integration with handle_extras() + future DB scaling
"""

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import re
from django.db.models import Prefetch
from mscrInventory.models import (
    Ingredient,
    ModifierBehavior,
    Packaging,
    RecipeModifier,
    SizeLabel,
)

def resolve_modifier_tree(modifier, depth=0, seen=None):
    """
    Recursively traverse expands_to relationships and return a flat list
    of all descendant modifiers (including the parent).

    Args:
        modifier (RecipeModifier): top-level modifier to resolve
        depth (int): recursion depth (used for safety/debugging)
        seen (set): IDs of visited modifiers to avoid infinite loops
    """
    if seen is None:
        seen = set()
    if not modifier or modifier.id in seen:
        return []
    seen.add(modifier.id)

    resolved = [modifier]
    for child in modifier.expands_to.all():
        resolved += resolve_modifier_tree(child, depth + 1, seen)
    return resolved

DEFAULT_SIZE_FALLBACK = "small"


def _normalize_label(value: str | None) -> str:
    return (value or "").strip().lower()


def _normalize_capacity_value(value) -> Decimal | None:
    if value is None:
        return None
    try:
        dec_value = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
    return dec_value.quantize(Decimal("0.1"))


def _discrete_unit_from_field(unit_field) -> str | None:
    if not unit_field:
        return None
    token = (
        getattr(unit_field, "abbreviation", None)
        or getattr(unit_field, "name", None)
        or ""
    ).strip().lower()
    if token in {"ea", "each", "unit", "units"}:
        return "unit"
    return None


def _infer_unit_type_from_instance(instance, fallback: str = "fluid_oz") -> str:
    if instance is None:
        return fallback
    discrete = _discrete_unit_from_field(getattr(instance, "unit_type", None))
    if discrete:
        return discrete
    type_field = getattr(instance, "type", None)
    if type_field and hasattr(type_field, "unit_type"):
        type_unit = getattr(type_field, "unit_type", None)
        if isinstance(type_unit, str) and type_unit:
            return type_unit
    return fallback


def _load_packaging_index():
    label_aliases: dict[str, str] = {}
    canonical_labels: set[str] = set()
    for label in SizeLabel.objects.all():
        canonical = _normalize_label(label.label)
        if not canonical:
            continue
        canonical_labels.add(canonical)
        label_aliases[canonical] = canonical
        display = _normalize_label(label.get_label_display())
        if display:
            label_aliases.setdefault(display, canonical)

    packaging_lookup: dict[tuple[str, str], dict] = {}
    capacity_lookup: dict[Decimal, str] = {}
    min_capacity = None
    min_capacity_label = None

    packaging_qs = (
        Packaging.objects.select_related("container", "type", "unit_type")
        .prefetch_related(
            "size_labels",
            Prefetch(
                "expands_to",
                queryset=Ingredient.objects.select_related("type", "unit_type"),
            ),
        )
    )

    for packaging in packaging_qs:
        size_labels = list(packaging.size_labels.all())
        if not size_labels:
            continue
        capacity = _normalize_capacity_value(
            getattr(getattr(packaging, "container", None), "capacity", None)
        )
        multiplier = Decimal(str(packaging.multiplier or 1.0))
        temps: list[str] = []
        if packaging.temp == "both":
            temps = ["hot", "cold"]
        elif packaging.temp in {"hot", "cold"}:
            temps = [packaging.temp]
        elif packaging.temp == "n/a":
            temps = []

        entry = {
            "packaging": packaging,
            "capacity": capacity,
            "multiplier": multiplier,
            "expands_to": list(packaging.expands_to.all()),
        }

        for size_label in size_labels:
            canonical = _normalize_label(size_label.label)
            if not canonical:
                continue
            canonical_labels.add(canonical)
            label_aliases.setdefault(canonical, canonical)
            display = _normalize_label(size_label.get_label_display())
            if display:
                label_aliases.setdefault(display, canonical)
            if capacity is not None:
                capacity_lookup.setdefault(capacity, canonical)
                if min_capacity is None or capacity < min_capacity:
                    min_capacity = capacity
                    min_capacity_label = canonical
            for temp in temps:
                packaging_lookup[(temp, canonical)] = entry

    if min_capacity_label:
        default_label = min_capacity_label
    elif DEFAULT_SIZE_FALLBACK in canonical_labels:
        default_label = DEFAULT_SIZE_FALLBACK
    elif canonical_labels:
        default_label = sorted(canonical_labels)[0]
    else:
        default_label = DEFAULT_SIZE_FALLBACK

    return {
        "label_aliases": label_aliases,
        "capacity_lookup": capacity_lookup,
        "default_label": default_label,
        "packaging_lookup": packaging_lookup,
    }


def _extract_numeric_volume(text: str) -> Decimal | None:
    if not text:
        return None
    text = text.lower()
    patterns = [
        (re.compile(r"(\d+(?:\.\d+)?)\s*[-\s]*(?:oz|ounce|ounces)"), Decimal("1")),
        (re.compile(r"(\d+(?:\.\d+)?)\s*[-\s]*(?:gal|gallon|gallons)"), Decimal("128")),
    ]
    for pattern, multiplier in patterns:
        match = pattern.search(text)
        if not match:
            continue
        try:
            value = Decimal(match.group(1))
        except InvalidOperation:
            continue
        volume = value * multiplier
        normalized = _normalize_capacity_value(volume)
        if normalized is not None:
            return normalized
    return None


def _match_label_from_aliases(text: str, aliases: dict[str, str]) -> str | None:
    for token, canonical in aliases.items():
        if not token:
            continue
        if re.search(rf"\b{re.escape(token)}\b", text):
            return canonical
    return None

def infer_temp_and_size(product_name: str, descriptors: list[str] | None = None):
    """
    Infer temperature (hot/cold) and size label from product name and modifiers.

    Args:
        product_name: The base item name (e.g., "Nitro Coldbrew", "Latte")
        descriptors:  List of strings such as ["iced", "medium", "whole milk"]

    Returns:
        (temp_type, size_label): ('hot'|'cold', 'small'|'medium'|'large'|'xl')
    """
    name = (product_name or "").lower()
    desc_str = " ".join(descriptors or []).lower()

    # --- Temperature inference --------------------------------------------
    cold_keywords = ["iced", "ice", "cold", "coldbrew", "nitro", "frappe", "smoothie", "refresher"]
    hot_keywords = ["hot", "steamed", "espresso", "latte", "americano", "tea"]

    temp_type = "cold" if any(k in name or k in desc_str for k in cold_keywords) else "hot"
    if any(token.strip() == "iced" for token in descriptors or []):
        temp_type = "cold"
    # edge: explicitly mark "hot" if name says "hot" even when other cold words exist
    if any(k in name or k in desc_str for k in hot_keywords):
        if "iced" not in desc_str and "cold" not in desc_str and "coldbrew" not in name:
            temp_type = "hot"

    packaging_index = _load_packaging_index()
    aliases = packaging_index["label_aliases"]
    capacity_lookup = packaging_index["capacity_lookup"]
    size_label = packaging_index["default_label"] or DEFAULT_SIZE_FALLBACK

    label_match = _match_label_from_aliases(name, aliases) or _match_label_from_aliases(
        desc_str, aliases
    )
    if label_match:
        size_label = label_match
    else:
        volume = _extract_numeric_volume(name) or _extract_numeric_volume(desc_str)
        if volume is not None and volume in capacity_lookup:
            size_label = capacity_lookup[volume]

    return temp_type, size_label

def round_qty(value: Decimal, unit_type: str) -> Decimal:
    """Round quantities to avoid trailing digits."""
    if unit_type == "unit":  # cookies, espresso shots, etc.
        return value.to_integral_value(rounding=ROUND_HALF_UP)
    # round to nearest 0.5 oz
    return (value * 2).to_integral_value(rounding=ROUND_HALF_UP) / 2


# ---------------------------------------------------------------------
# Main aggregator
# ---------------------------------------------------------------------
def aggregate_ingredient_usage(
    recipe_items,
    resolved_modifiers=None,
    temp_type: str | None = None,
    size: str | None = None,
    overrides_map: dict[str, dict] | None = None,
    is_drink: bool = True,
    include_cup: bool = True,
):
    """
    Aggregate all ingredient usage for a given product, scaled to size.

    - Base recipe quantities are scaled by Packaging.multiplier when is_drink is True.
    - Modifiers are added with estimated or defined quantities.
    - Optional overrides_map lets callers provide the resolved recipe map after
      handle_extras(), ensuring Barista's Choice expansions adjust the base
      ingredient totals before rebalancing.
    - Total drink volume is normalized to cup size (so the main liquid fills the rest)
      when the product represents a drink.

    Returns:
        usage_summary: {ingredient_name: {"qty": Decimal, "sources": [str]}}
    """
    packaging_index = _load_packaging_index()
    default_size = packaging_index["default_label"] or DEFAULT_SIZE_FALLBACK
    resolved_temp = _normalize_label(temp_type or "cold") or "cold"
    resolved_size = _normalize_label(size) or default_size
    packaging_lookup = packaging_index["packaging_lookup"]
    packaging_entry = packaging_lookup.get((resolved_temp, resolved_size))
    if not packaging_entry and resolved_size != default_size:
        packaging_entry = packaging_lookup.get((resolved_temp, default_size))

    scale_factor = Decimal("1.0")
    cup_capacity = None
    if is_drink and packaging_entry:
        scale_factor = packaging_entry["multiplier"]
        cup_capacity = packaging_entry.get("capacity")
    elif is_drink:
        scale_factor = Decimal("1.0")

    usage_summary = {}
    primary_liquid_key: str | None = None
    overrides_map = overrides_map or {}
    ingredient_cache: dict[str, Ingredient | None] = {}

    def _get_ingredient(name: str) -> Ingredient | None:
        if name in ingredient_cache:
            return ingredient_cache[name]
        ing = (
            Ingredient.objects.filter(name__iexact=name)
            .select_related("type", "unit_type")
            .first()
        )
        ingredient_cache[name] = ing
        return ing

    def _get_unit_type(name: str, fallback: str = "fluid_oz") -> str:
        if name in usage_summary and "unit_type" in usage_summary[name]:
            return usage_summary[name]["unit_type"]
        ing = _get_ingredient(name)
        if ing:
            return _infer_unit_type_from_instance(ing, fallback)
        return fallback

    def _add_packaging_usage(entry: dict):
        if not entry:
            return
        packaging_obj = entry.get("packaging")
        expands = entry.get("expands_to") or []

        def _add_item(ingredient, source_label: str):
            if not ingredient:
                return
            name = ingredient.name
            usage_summary[name] = {
                "qty": Decimal("1.0"),
                "sources": [source_label],
                "unit_type": _infer_unit_type_from_instance(ingredient, "unit"),
            }
            ingredient_cache[name] = ingredient

        _add_item(packaging_obj, "packaging")
        for extra in expands:
            _add_item(extra, "packaging_expands")

    if is_drink and include_cup and packaging_entry:
        _add_packaging_usage(packaging_entry)

    # --- Base recipe scaling -----------------------------------------------
    for ri in recipe_items:
        ing = ri.ingredient
        base_qty = ri.quantity or Decimal("0.0")
        if not is_drink:
            scaled_qty = base_qty
        else:
            scaled_qty = base_qty * scale_factor

        unit_type = _infer_unit_type_from_instance(ing)
        scaled_qty = round_qty(scaled_qty, unit_type)

        usage_summary[ing.name] = {
            "qty": scaled_qty,
            "sources": ["base_recipe"],
            "unit_type": unit_type,
        }
        if unit_type != "unit":
            if primary_liquid_key is None:
                primary_liquid_key = ing.name
            else:
                current_qty = usage_summary[primary_liquid_key]["qty"]
                if scaled_qty > current_qty:
                    primary_liquid_key = ing.name

    # Apply any overrides from resolved recipe maps (e.g., Barista's Choice)
    for name, meta in overrides_map.items():
        qty = meta.get("qty")
        if qty is None:
            continue
        try:
            qty_value = Decimal(str(qty))
        except Exception:
            continue

        existed_before = name in usage_summary
        unit_type = usage_summary.get(name, {}).get("unit_type")
        previous_qty = usage_summary.get(name, {}).get("qty") if existed_before else None

        if not unit_type:
            fallback_type = meta.get("type")
            unit_type = _get_unit_type(name, "unit" if fallback_type == "UNIT" else "fluid_oz")

        scaled_qty = round_qty(qty_value * scale_factor, unit_type)

        changed = (not existed_before) or (previous_qty != scaled_qty)

        if name in usage_summary:
            if changed:
                usage_summary[name]["qty"] = scaled_qty
            if changed and "override_from_recipe" not in usage_summary[name]["sources"]:
                usage_summary[name]["sources"].append("override_from_recipe")
        else:
            usage_summary[name] = {
                "qty": scaled_qty,
                "sources": ["override_from_recipe"],
                "unit_type": unit_type,
            }

    # --- Track total liquid capacity (estimated) ----------------------------
    # --- Apply modifiers ----------------------------------------------------
    # resolved modifiers may continue adjusting liquid totals
    if resolved_modifiers:
        for mod in resolved_modifiers:
            ing = getattr(mod, "ingredient", None)
            if not ing:
                continue

            name = ing.name
            unit_type = getattr(ing.type, "unit_type", "fluid_oz")

            # Use base_quantity if defined, else default to 1 fl oz
            base_qty = getattr(mod, "base_quantity", Decimal("1.0"))
            qty = round_qty(base_qty * scale_factor, unit_type)

            behavior = getattr(mod, "behavior", ModifierBehavior.ADD)

            if behavior == ModifierBehavior.REPLACE:
                existing_sources = usage_summary.get(name, {}).get("sources", [])
                sources = list(dict.fromkeys(existing_sources + ["modifier_replace"]))
                usage_summary[name] = {
                    "qty": qty,
                    "sources": sources or ["modifier_replace"],
                    "unit_type": unit_type,
                }
                if unit_type != "unit":
                    if primary_liquid_key is None:
                        primary_liquid_key = name
                    else:
                        current = usage_summary.get(primary_liquid_key, {}).get("qty", Decimal("0.0"))
                        if qty >= current:
                            primary_liquid_key = name
                continue

            if behavior == ModifierBehavior.SCALE:
                factor = getattr(mod, "quantity_factor", Decimal("1.0"))
                target = name if name in usage_summary else None
                if not target:
                    target = ing.name if ing.name in usage_summary else None
                if target:
                    current_qty = usage_summary[target]["qty"]
                    new_qty = round_qty(current_qty * factor, usage_summary[target]["unit_type"])
                    usage_summary[target]["qty"] = new_qty
                    usage_summary[target]["sources"].append("modifier_scale")
                continue

            usage_summary[name] = usage_summary.get(
                name, {"qty": Decimal("0.0"), "sources": [], "unit_type": unit_type}
            )
            usage_summary[name]["qty"] += qty
            usage_summary[name]["sources"].append("modifier_add")

    # --- Rebalance main liquid (if any) -------------------------------------
    # Find main base liquid (typically something like 'Cold Brew', 'Espresso', 'Tea')
    main_liquid_key = None
    for k, meta in usage_summary.items():
        if meta.get("unit_type") == "unit":
            continue
        lower = k.lower()
        ing = _get_ingredient(k)
        type_name = _normalize_label(getattr(getattr(ing, "type", None), "name", ""))
        matches_refresher_type = type_name == "refresher base"
        if any(token in lower for token in ("brew", "tea", "milk", "cream")) or matches_refresher_type: # Removed 'coffee' to exclude 'green coffee extract'
            main_liquid_key = k
            break
    if not main_liquid_key:
        main_liquid_key = primary_liquid_key

    if (
        is_drink
        and cup_capacity is not None
        and main_liquid_key
        and main_liquid_key in usage_summary
    ):
        other_volume = Decimal("0.0")
        for key, meta in usage_summary.items():
            if key == main_liquid_key:
                continue
            if meta.get("unit_type") == "unit":
                continue
            other_volume += meta.get("qty", Decimal("0.0"))

        remaining_volume = cup_capacity - other_volume
        remaining_volume = max(remaining_volume, Decimal("0.0"))

        usage_summary[main_liquid_key]["qty"] = round_qty(
            remaining_volume, usage_summary[main_liquid_key]["unit_type"]
        )
        usage_summary[main_liquid_key]["sources"].append("rebalanced_to_fill")

    # --- Round output + cleanup --------------------------------------------
    for k, v in usage_summary.items():
        v["qty"] = round_qty(v["qty"], v["unit_type"])
        v.pop("unit_type", None)

    return usage_summary
