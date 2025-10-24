"""
handle_extras.py
----------------
Database-driven modifier expansion and adjustment logic.

This module provides reusable functions for parsing and applying
RecipeModifier behavior to in-memory recipe maps. Used by SquareImporter,
and designed to extend to future importers (e.g. Shopify, Doordash).
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, Tuple, List, Optional
from mscrInventory.models import Ingredient, RecipeModifier, ModifierBehavior

def _select_targets(recipe_map, by_type=None, by_name=None):
    """Return [(ingredient_name, meta)] matching type or name."""
    by_type = {t.strip().upper() for t in (by_type or [])}
    by_name = {n.strip().lower() for n in (by_name or [])}
    out = []

    for ing, meta in recipe_map.items():
        ing_name = ing if isinstance(ing, str) else getattr(ing, "name", "")
        ing_type = (meta.get("type") or "").upper()

        if (
            (by_type and ing_type in by_type)
            or (by_name and ing_name.lower() in by_name)
            or (not by_type and not by_name)
        ):
            out.append((ing_name, meta))
    return out


def _add_ingredient(recipe_map, name, qty, type_hint=None):
    """Add (or increment) an ingredient safely."""
    if not name:
        return
    if name in recipe_map:
        recipe_map[name]["qty"] = (
            recipe_map[name]["qty"] + Decimal(qty)
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        recipe_map[name] = {
            "qty": Decimal(qty).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "type": type_hint or "",
        }

def _remove_ingredient(recipe_map: Dict[Ingredient, Dict], ing: Ingredient):
    recipe_map.pop(ing, None)

def _resolve_ingredient_by_name(name: str) -> Optional[Ingredient]:
    return Ingredient.objects.filter(name__iexact=name.strip()).first()

# ---------------------------------------------------------------------
# MAIN HANDLER
# ---------------------------------------------------------------------

def handle_extras(modifier_name: str, recipe_map: dict, normalized_modifiers: list):
    """Apply RecipeModifier rules to a recipe_map."""

    from mscrInventory.models import RecipeModifier, ModifierBehavior

    try:
        mod = RecipeModifier.objects.get(name__iexact=modifier_name)
    except RecipeModifier.DoesNotExist:
        return recipe_map

    # Safely parse JSON fields
    sel_types = []
    sel_names = []
    if isinstance(mod.target_selector, dict):
        sel_types = mod.target_selector.get("by_type", [])
        sel_names = mod.target_selector.get("by_name", [])

    quantity_factor = getattr(mod, "quantity_factor", Decimal("1.0")) or Decimal("1.0")

    # --- SCALE ----------------------------------------------------------
    if mod.behavior == ModifierBehavior.SCALE:
        targets = _select_targets(recipe_map, by_type=sel_types, by_name=sel_names)
        for ing, meta in targets:
            meta["qty"] = (
                Decimal(meta["qty"]) * Decimal(quantity_factor)
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    # --- REPLACE --------------------------------------------------------
    elif mod.behavior == ModifierBehavior.REPLACE and mod.replaces:
        targets = _select_targets(recipe_map, by_type=sel_types, by_name=sel_names)

        # total quantity of removed items (to preserve overall volume)
        total_qty = Decimal("0.0")
        removed_keys = []

        for ing, meta in targets:
            total_qty += Decimal(meta.get("qty", 0))
            removed_keys.append(ing)

        # remove matched keys case-insensitively
        for key in removed_keys:
            for existing in list(recipe_map.keys()):
                if existing.lower() == key.lower():
                    recipe_map.pop(existing, None)

        # add new replacements scaled to the removed total
        for name, factor in (mod.replaces.get("to", []) or []):
            _add_ingredient(
                recipe_map,
                name,
                (Decimal(factor) * total_qty).quantize(Decimal("0.01")),
                type_hint=mod.type,
            )

    # --- ADD ------------------------------------------------------------
    elif mod.behavior == ModifierBehavior.ADD:
        _add_ingredient(
            recipe_map,
            mod.ingredient.name,
            Decimal(mod.base_quantity),
            type_hint=mod.type,
        )

    # --- EXPANSIONS -----------------------------------------------------
    for expanded in mod.expands_to.all():
        if expanded.behavior == ModifierBehavior.ADD:
            _add_ingredient(
                recipe_map,
                expanded.ingredient.name,
                Decimal(expanded.base_quantity),
                type_hint=expanded.type,
            )
        else:
            recipe_map = handle_extras(expanded.name, recipe_map, normalized_modifiers)

    # --- FINALIZE -------------------------------------------------------
    return recipe_map