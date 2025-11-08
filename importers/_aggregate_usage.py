"""
_aggregate_usage.py
-------------------
Ingredient usage aggregation with size/temperature scaling.

This version:
- Scales recipes based on inferred size + temperature
- Rounds generously (½ oz for liquids, whole units for discrete)
- Prepares for integration with handle_extras() + future DB scaling
"""

from decimal import Decimal, ROUND_HALF_UP
import re
from mscrInventory.models import Ingredient, RecipeModifier, ModifierBehavior

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

# ---------------------------------------------------------------------
# Prototype scaling config (temporary, later DB-backed)
# ---------------------------------------------------------------------
"""Size and temperature scaling factors:
    - Hot Drinks come in 12oz (small) and 20oz (large)
    - Cold Drinks come in 16oz (small), 32oz (xl)
    - All Recipes are based on 12oz base. 
"""
SIZE_SCALE = {
    "hot":  {"small": 1.0, "large": 1.67},
    "cold": {"small": 1.34, "xl": 2.0, "growler": 4.0},
}

# ---------------------------------------------------------------------
# Default cups by temperature & size
# ---------------------------------------------------------------------
CUP_MAP = {
    "hot": {
        "small": "12oz Cup",
        "medium": "16oz Cup",
        "large": "20oz Cup",
        "xl": "20oz Cup",
    },
    "cold": {
        "small": "16oz Cup",
        "medium": "24oz Cup",
        "large": "24oz Cup",
        "xl": "32oz Cup",
        "growler": "64oz Growler"
    },
}

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

    # --- Size inference ---------------------------------------------------
    size_map = {
        "growler": ["growler", "64oz", "64 oz", "64-ounce", "64 ounce"],
        "xl": ["xl", "extra large", "x-large", "32oz", "32 oz"],
        "large": ["large", "20oz", "20 oz"],
        "medium": ["medium", "med"],
        "small": ["small", "short", "12oz", "12 oz", "16oz", "16 oz", "10oz"],
    }

    size_label = "small"  # default
    for label, patterns in size_map.items():
        if any(re.search(rf"\b{p}\b", desc_str) or re.search(rf"\b{p}\b", name) for p in patterns):
            size_label = label
            break

    # --- Fallbacks --------------------------------------------------------
    # E.g., “Latte” without “iced” → assume hot/small
    # E.g., “Cold Brew” without size → assume cold/small
    normalized_name = re.sub(r"[\s-]", "", name)
    normalized_desc = re.sub(r"[\s-]", "", desc_str)
    if (
        "growler" in name
        or "growler" in desc_str
        or "64oz" in normalized_name
        or "64oz" in normalized_desc
        or "64ounce" in normalized_name
        or "64ounce" in normalized_desc
    ):
        size_label = "growler"
    elif "coldbrew" in name and size_label == "small":
        size_label = "small"  # typical default for cold drinks

    return temp_type, size_label

def get_default_cup(temp_type: str, size: str) -> str | None:
    return CUP_MAP.get(temp_type, {}).get(size)

def get_scale(temp_type: str, size: str) -> Decimal:
    """Get scaling factor for given temperature + size."""
    return Decimal(str(SIZE_SCALE.get(temp_type, {}).get(size, 1.0)))

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

    - Base recipe quantities are scaled by get_scale() when is_drink is True.
    - Modifiers are added with estimated or defined quantities.
    - Optional overrides_map lets callers provide the resolved recipe map after
      handle_extras(), ensuring Barista's Choice expansions adjust the base
      ingredient totals before rebalancing.
    - Total drink volume is normalized to cup size (so the main liquid fills the rest)
      when the product represents a drink.

    Returns:
        usage_summary: {ingredient_name: {"qty": Decimal, "sources": [str]}}
    """
    scale_factor = get_scale(temp_type or "cold", size or "small") if is_drink else Decimal("1.0")
    usage_summary = {}
    primary_liquid_key: str | None = None
    overrides_map = overrides_map or {}
    ingredient_cache: dict[str, Ingredient | None] = {}

    def _get_unit_type(name: str, fallback: str = "fluid_oz") -> str:
        if name in usage_summary and "unit_type" in usage_summary[name]:
            return usage_summary[name]["unit_type"]
        if name in ingredient_cache:
            ing = ingredient_cache[name]
        else:
            ing = (
                Ingredient.objects.filter(name__iexact=name)
                .select_related("type")
                .first()
            )
            ingredient_cache[name] = ing
        if ing and getattr(ing, "type", None) and getattr(ing.type, "unit_type", None):
            return ing.type.unit_type
        return fallback

    # --- Add cup as inventory item automatically -------------------------
    # I call this auto_cup() a lot
    cup_name = get_default_cup(temp_type, size) if (is_drink and include_cup) else None
    if cup_name:
        usage_summary[cup_name] = {
            "qty": Decimal("1.0"),  # one per drink
            "sources": ["auto_cup"],
            "unit_type": "unit",
        }

    # --- Base recipe scaling -----------------------------------------------
    for ri in recipe_items:
        ing = ri.ingredient
        base_qty = ri.quantity or Decimal("0.0")
        if not is_drink:
            scaled_qty = base_qty
        else:
            scaled_qty = base_qty * scale_factor

        unit_type = getattr(ing.type, "unit_type", "fluid_oz")
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
    cup_size_map = {
        ("hot", "small"): 12,
        ("hot", "medium"): 16,
        ("hot", "large"): 20,
        ("hot", "xl"): 20,
        ("cold", "small"): 16,
        ("cold", "medium"): 24,
        ("cold", "large"): 24,
        ("cold", "xl"): 32,
    }
    cup_capacity = Decimal(str(cup_size_map.get((temp_type, size), 16))) if is_drink else None

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
    for k in usage_summary.keys():
        lower = k.lower()
        if any(token in lower for token in ("brew", "coffee", "tea", "milk", "cream")):
            main_liquid_key = k
            break
    if not main_liquid_key:
        main_liquid_key = primary_liquid_key

    if is_drink and cup_capacity and main_liquid_key and main_liquid_key in usage_summary:
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
