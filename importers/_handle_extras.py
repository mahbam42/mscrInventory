"""
handle_extras.py
----------------
Database-driven modifier expansion and adjustment logic.

This module provides reusable functions for parsing and applying
RecipeModifier behavior to in-memory recipe maps. Used by SquareImporter,
and designed to extend to future importers (e.g. Shopify, Doordash).
"""

from decimal import Decimal
from typing import Dict, Iterable, Tuple, List, Optional
from mscrInventory.models import Ingredient, RecipeModifier, ModifierBehavior

# --- selection helpers -------------------------------------------------

def _select_targets(
    recipe_map: Dict[Ingredient, Dict],
    by_type: Optional[Iterable[str]] = None,
    by_name: Optional[Iterable[str]] = None,
) -> List[Tuple[Ingredient, Dict]]:
    """Return [(ingredient, meta)] from recipe_map matching any type or name."""
    by_type = {t.strip().upper() for t in (by_type or [])}
    by_name = {n.strip().lower() for n in (by_name or [])}
    out = []
    for ing, meta in recipe_map.items():
        ing_type = (meta.get("type") or getattr(getattr(ing, "type", None), "name", "")).upper()
        if (by_type and ing_type in by_type) or (by_name and ing.name.lower() in by_name) or (not by_type and not by_name):
            out.append((ing, meta))
    return out

def _add_ingredient(recipe_map: Dict[Ingredient, Dict], ing: Ingredient, qty: Decimal, ing_type: Optional[str] = None):
    """Add/accumulate an ingredient in the working recipe map."""
    if ing in recipe_map:
        recipe_map[ing]["qty"] = recipe_map[ing]["qty"] + qty
    else:
        recipe_map[ing] = {"qty": qty, "type": ing_type or getattr(getattr(ing, "type", None), "name", None)}

def _remove_ingredient(recipe_map: Dict[Ingredient, Dict], ing: Ingredient):
    recipe_map.pop(ing, None)

def _resolve_ingredient_by_name(name: str) -> Optional[Ingredient]:
    return Ingredient.objects.filter(name__iexact=name.strip()).first()

# --- main: handle_extras -----------------------------------------------

def handle_extras(modifier_name: str, recipe_map: Dict[Ingredient, Dict], normalized_modifiers: List[Dict]):
    """
    Apply DB-defined RecipeModifier effects to the in-memory recipe_map.

    - Supports ADD (adds expands_to * quantity_factor)
    - Supports REPLACE by type or name (replaces -> to list with optional weights)
    - Supports SCALE by type or name (multiplies qty by quantity_factor)
    - Composite effects naturally supported by combining replaces + expands_to in one modifier (e.g., Dirty Chai)
    """
    mod = (
        RecipeModifier.objects.filter(name__iexact=modifier_name).first()
        or RecipeModifier.objects.filter(name__icontains=modifier_name.strip()).first()
    )
    if not mod:
        return  # unknown/irrelevant → no-op

    selector = (mod.target_selector or {})
    sel_types = selector.get("by_type") or []
    sel_names = selector.get("by_name") or []

    # 1) REPLACE: target by type or name, swap to one or many ingredients
    if mod.behavior == ModifierBehavior.REPLACE:
        # Targets to remove
        targets = _select_targets(recipe_map, by_type=sel_types, by_name=sel_names)
        # Who to replace with
        rep = (mod.replaces or {})
        to_list = rep.get("to") or []  # list of [name, weight]
        # If to_list contains single string, normalize to [[name, 1.0]]
        if to_list and isinstance(to_list[0], str):
            to_list = [[to_list[0], 1.0]]

        # Remove targets
        for ing, _meta in targets:
            _remove_ingredient(recipe_map, ing)

        # Add replacements (weights scaled by quantity_factor)
        for name, weight in to_list:
            repl_ing = _resolve_ingredient_by_name(name)
            if repl_ing:
                factor = Decimal(mod.quantity_factor) * Decimal(str(weight or 1.0))
                _add_ingredient(recipe_map, repl_ing, factor)

    # 2) ADD: add expands_to ingredients (each * quantity_factor)
    if mod.behavior == ModifierBehavior.ADD:
        for ing in mod.expands_to.all():
            _add_ingredient(recipe_map, ing, Decimal(mod.quantity_factor))

    # 3) SCALE: multiply qty for selected targets
    if mod.behavior == ModifierBehavior.SCALE:
        targets = _select_targets(recipe_map, by_type=sel_types, by_name=sel_names)
        for ing, meta in targets:
            meta["qty"] = (meta.get("qty") or Decimal(1)) * Decimal(mod.quantity_factor)

    # Record normalized modifier for logging/analytics (optional)
    normalized_modifiers.append({
        "name": mod.name,
        "behavior": mod.behavior,
        "quantity": Decimal(mod.quantity_factor),
        "targets_by_type": sel_types,
        "targets_by_name": sel_names,
    })