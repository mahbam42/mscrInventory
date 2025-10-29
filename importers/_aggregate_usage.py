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
from mscrInventory.models import Ingredient, RecipeModifier

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
        "large": "20oz Cup",
    },
    "cold": {
        "small": "16oz Cup",
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
    cold_keywords = ["iced", "cold", "coldbrew", "nitro", "frappe", "smoothie", "refresher"]
    hot_keywords = ["hot", "steamed", "espresso", "latte", "americano", "tea"]

    temp_type = "cold" if any(k in name or k in desc_str for k in cold_keywords) else "hot"
    # edge: explicitly mark "hot" if name says "hot" even when other cold words exist
    if any(k in name or k in desc_str for k in hot_keywords):
        if "iced" not in desc_str and "cold" not in desc_str and "coldbrew" not in name:
            temp_type = "hot"

    # --- Size inference ---------------------------------------------------
    size_map = {
        "xl": ["xl", "extra large", "x-large", "32oz", "32 oz"],
        "large": ["large", "20oz", "20 oz"],
        #"medium": ["medium", "16oz", "16 oz"],
        "small": ["small", "short", "12oz", "12 oz"],
    }

    size_label = "small"  # default
    for label, patterns in size_map.items():
        if any(re.search(rf"\b{p}\b", desc_str) or re.search(rf"\b{p}\b", name) for p in patterns):
            size_label = label
            break

    # --- Fallbacks --------------------------------------------------------
    # E.g., “Latte” without “iced” → assume hot/small
    # E.g., “Cold Brew” without size → assume cold/small
    if "coldbrew" in name and size_label == "small":
        size_label = "medium"  # typical default for cold drinks

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
def aggregate_ingredient_usage(recipe_items, resolved_modifiers=None,
                               temp_type: str | None = None,
                               size: str | None = None):
    """
    Aggregate all ingredient usage for a given product, scaled to size.

    - Base recipe quantities are scaled by get_scale().
    - Modifiers are added with estimated or defined quantities.
    - Total drink volume is normalized to cup size (so the main liquid fills the rest).

    Returns:
        usage_summary: {ingredient_name: {"qty": Decimal, "sources": [str]}}
    """
    scale_factor = get_scale(temp_type or "cold", size or "small")
    usage_summary = {}

    # --- Add cup as inventory item automatically -------------------------
    cup_name = get_default_cup(temp_type, size)
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
        scaled_qty = base_qty * scale_factor

        unit_type = getattr(ing.type, "unit_type", "fluid_oz")
        scaled_qty = round_qty(scaled_qty, unit_type)

        usage_summary[ing.name] = {
            "qty": scaled_qty,
            "sources": ["base_recipe"],
            "unit_type": unit_type,
        }

    # --- Track total liquid capacity (estimated) ----------------------------
    cup_size_map = {
        ("hot", "small"): 12,
        ("hot", "large"): 20,
        ("cold", "small"): 16,
        ("cold", "xl"): 32,
    }
    cup_capacity = Decimal(str(cup_size_map.get((temp_type, size), 16)))

    # --- Apply modifiers ----------------------------------------------------
    total_modifier_volume = Decimal("0.0")
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

            usage_summary[name] = usage_summary.get(
                name, {"qty": Decimal("0.0"), "sources": [], "unit_type": unit_type}
            )
            usage_summary[name]["qty"] += qty
            usage_summary[name]["sources"].append("modifier_add")

            if unit_type != "unit":  # only count liquids toward fill volume
                total_modifier_volume += qty

    # --- Rebalance main liquid (if any) -------------------------------------
    # Find main base liquid (typically something like 'Cold Brew', 'Espresso', 'Tea')
    main_liquid_key = None
    for k in usage_summary.keys():
        if "brew" in k.lower() or "coffee" in k.lower() or "tea" in k.lower():
            main_liquid_key = k
            break

    if main_liquid_key:
        remaining_volume = cup_capacity - total_modifier_volume
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
