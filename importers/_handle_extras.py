"""
_handle_extras.py
-----------------
Context-aware modifier logic for Square imports.

Goals:
• Contain all "smart" expansion and replacement rules.
• Operate only within the current recipe context (no global scans).
• Log clear, human-readable dry-run actions.
"""

from decimal import Decimal
from typing import Dict, List, Optional, Iterable
from mscrInventory.models import Ingredient, RecipeModifier, Recipe, ModifierBehavior
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _normalize_token(token: str) -> str:
    """Lowercase and strip punctuation for fuzzy comparisons."""
    return token.strip().lower().replace("’", "'").replace("–", "-")


def _select_targets(recipe_map: Dict[str, Dict], current_context: Optional[List[str]] = None,
                    by_type: Optional[Iterable[str]] = None,
                    by_name: Optional[Iterable[str]] = None) -> List[str]:
    """
    Restrict matches to ingredients within the current recipe context.
    """
    if current_context:
        recipe_map = {k: v for k, v in recipe_map.items() if k in current_context}

    by_type = {t.upper() for t in (by_type or [])}
    by_name = {_normalize_token(n) for n in (by_name or [])}

    matches = []
    for ing_name, meta in recipe_map.items():
        ing_type = (meta.get("type") or "").upper()
        if (by_type and ing_type in by_type) or (_normalize_token(ing_name) in by_name):
            matches.append(ing_name)

    return matches


def _lookup_modifier_or_recipe(name: str) -> Optional[object]:
    """
    Try to resolve a name to a RecipeModifier or Recipe (preset drink).
    """
    name_norm = _normalize_token(name)
    mod = RecipeModifier.objects.filter(name__icontains=name_norm).first()
    if mod:
        return mod

    recipe = Recipe.objects.filter(name__icontains=name_norm).first()
    if recipe:
        return recipe

    return None


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def handle_extras(modifier_name: str,
                  recipe_map: Dict[str, Dict],
                  normalized_modifiers: List[str],
                  recipe_context: Optional[List[str]] = None,
                  verbose: bool = False) -> Dict[str, Dict]:
    """
    Expand, scale, or replace ingredients based on modifier rules.

    Args:
        modifier_name: Raw modifier text from Square.
        recipe_map: Ingredient name → {qty, type}.
        normalized_modifiers: All parsed modifiers for this item.
        recipe_context: Optional list of ingredient names in the base recipe.
        verbose: If True, print/log each operation (for dry-run mode).

    Returns:
        Updated recipe_map (copy).
    """
    result = recipe_map.copy()
    name_norm = _normalize_token(modifier_name)
    target = _lookup_modifier_or_recipe(modifier_name)

    if not target:
        if verbose:
            print(f"⚠️  No modifier or recipe found for '{modifier_name}'")
        return result

    # -----------------------------------------------------------------------
    # Case 1: Modifier is actually a recipe (e.g., Cherry Dipped Vanilla)
    # -----------------------------------------------------------------------
    if isinstance(target, Recipe):
        if verbose:
            print(f"🧩 '{modifier_name}' recognized as recipe preset → expanding")
        for item in target.recipe_items.all():
            result[item.ingredient.name] = {
                "qty": item.quantity,
                "type": item.ingredient.type.name if item.ingredient.type else "",
            }
        return result

    # -----------------------------------------------------------------------
    # Case 2: Modifier is a RecipeModifier
    # -----------------------------------------------------------------------
    mod = target
    behavior = getattr(mod, "behavior", ModifierBehavior.ADD)
    quantity_factor = getattr(mod, "quantity_factor", Decimal("1.0"))
    sel = getattr(mod, "target_selector", {}) or {}
    by_type = sel.get("by_type", [])
    by_name = sel.get("by_name", [])

    matched = _select_targets(result, recipe_context, by_type, by_name)

    if verbose:
        print(f"🧩 Modifier: {modifier_name} ({behavior})")
        print(f"   → Matches in context: {matched or 'none'}")

    # --- ADD ---------------------------------------------------------------
    if behavior == ModifierBehavior.ADD:
        result[mod.ingredient.name] = {
            "qty": getattr(mod, "base_quantity", Decimal("1.0")),
            "type": mod.type,
        }
        if verbose:
            print(f"   ➕ Added {mod.ingredient.name} ×{mod.base_quantity}")

    # --- REPLACE -----------------------------------------------------------
    elif behavior == ModifierBehavior.REPLACE:
        for m in matched:
            del result[m]
            if verbose:
                print(f"   🔁 Replaced {m} → {mod.ingredient.name}")
        result[mod.ingredient.name] = {
            "qty": getattr(mod, "base_quantity", Decimal("1.0")),
            "type": mod.type,
        }

    # --- SCALE -------------------------------------------------------------
    elif behavior == ModifierBehavior.SCALE:
        for m in matched:
            q = result[m]["qty"]
            result[m]["qty"] = (q * quantity_factor).quantize(Decimal("0.01"))
            if verbose:
                print(f"   📏 Scaled {m} ×{quantity_factor} → {result[m]['qty']}")

    # --- EXPANDS_TO (special combos) --------------------------------------
    for sub in mod.expands_to.all():
        result[sub.ingredient.name] = {
            "qty": getattr(sub, "base_quantity", Decimal("1.0")),
            "type": sub.type,
        }
        if verbose:
            print(f"   🌱 Expanded to include {sub.ingredient.name}")

    return result
