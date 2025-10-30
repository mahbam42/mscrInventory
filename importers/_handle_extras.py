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
from mscrInventory.models import Ingredient, RecipeModifier, RecipeItem, ModifierBehavior, Product
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _normalize_token(token: str) -> str:
    """Lowercase and strip punctuation for fuzzy comparisons."""
    return token.strip().lower().replace("’", "'").replace("–", "-")


def normalize_modifier(raw: str) -> str:
    """
    Normalize a raw Square modifier string for matching.
    Examples:
        " Extra Flavor "   → "extra flavor"
        "1/2 Vanilla"      → "half vanilla"
        "Oat-Milk"         → "oat milk"
    """
    if not raw:
        return ""

    token = raw.strip().lower()
    token = token.replace("½", "half").replace("1/2", "half")
    token = token.replace("-", " ").replace("_", " ")
    token = token.replace("’", "'").replace("–", "-")

    while "  " in token:
        token = token.replace("  ", " ")

    return token


def _select_targets(recipe_map: Dict[str, Dict], current_context: Optional[List[str]] = None,
                    by_type: Optional[Iterable[str]] = None,
                    by_name: Optional[Iterable[str]] = None) -> List[str]:
    """Restrict matches to ingredients within the current recipe context."""
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
    """Try to resolve a name to a RecipeModifier or RecipeItem."""
    if not name:
        return None

    name_norm = _normalize_token(name)
    candidates = [name, name_norm]

    for token in candidates:
        mod = RecipeModifier.objects.filter(name__iexact=token).first()
        if mod:
            return mod

        mod = RecipeModifier.objects.filter(name__icontains=token).first()
        if mod:
            return mod

    recipe_item = RecipeItem.objects.filter(
        ingredient__name__icontains=name_norm
    ).select_related("ingredient").first()
    if recipe_item:
        return recipe_item

    return None


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def handle_extras(modifier_name: str,
                  recipe_map: Dict[str, Dict],
                  normalized_modifiers: List[str],
                  recipe_context: Optional[List[str]] = None,
                  verbose: bool = False):
    """
    Expand, scale, or replace ingredients based on modifier rules.
    Returns (result, changelog)
    """
    result = recipe_map.copy()
    name_norm = _normalize_token(modifier_name)
    target = _lookup_modifier_or_recipe(modifier_name)

    if not target:
        if verbose:
            print(f"⚠️  No modifier or recipe found for '{modifier_name}'")
        # Return empty changelog for consistency
        return result, {"added": [], "replaced": [], "behavior": None}

    # -----------------------------------------------------------------------
    # Case 1: Modifier is actually a recipe (e.g., Cherry Dipped Vanilla)
    # -----------------------------------------------------------------------
    """ if isinstance(target, RecipeItem):
        if verbose:
            print(f"🧩 '{modifier_name}' recognized as recipe preset → expanding")

        product = target.product  # get parent Product
        for item in product.recipe_items.all():
            result[item.ingredient.name] = {
                "qty": item.quantity,
                "type": item.ingredient.type.name if item.ingredient.type else "",
            }

        return result, {
            "added": [item.ingredient.name for item in product.recipe_items.all()],
            "replaced": [],
            "behavior": "EXPANDS",
        } """
    
    # -----------------------------------------------------------------------
    # Case 1: Modifier is actually a recipe (Barista’s Choice drink acting as a flavor modifier)
    # -----------------------------------------------------------------------
    from mscrInventory.models import Product

    recipe_product = Product.objects.filter(
        name__iexact=modifier_name.strip(),
        categories__name__iexact="Barista's Choice"
    ).first()

    if recipe_product:
        if verbose:
            print(f"🧩 Modifier: {modifier_name} (Barista’s Choice recipe) — expanding from recipe")

        duplicates = []
        for item in recipe_product.recipe_items.all():
            ing_name = item.ingredient.name
            ing_type = item.ingredient.type.name if item.ingredient.type else ""
            ing_qty = item.quantity

            if ing_name in result:
                duplicates.append(ing_name)
                result[ing_name]["qty"] += ing_qty
            else:
                result[ing_name] = {"qty": ing_qty, "type": ing_type}

        if duplicates and verbose:
            print(f"⚠️ Duplicate ingredients merged from {modifier_name}: {duplicates}")

        # These Tokens don't apply here
        IGNORED_TOKENS = {"iced", "ice", "hot", "small", "medium", "large", "xl"}

        if modifier_name.lower() in IGNORED_TOKENS:
            if verbose:
                print(f"🧊 Ignored size/temp token '{modifier_name}'")
            return result, {"added": [], "replaced": [], "behavior": "ignored_variant"}

        return result, {
            "added": [ri.ingredient.name for ri in recipe_product.recipe_items.all()],
            "behavior": "expand_from_recipe",
            "replaced": [],
        }

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
    replaced_entries = []

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
        for m in matched or []:
            if isinstance(m, (list, tuple)) and len(m) == 2:
                replaced_entries.append(tuple(m))
            elif isinstance(m, str):
                new_name = getattr(getattr(mod, "ingredient", None), "name", mod.name)
                replaced_entries.append((m, new_name))
            else:
                print(f"⚠️  Skipping malformed matched entry: {m!r}")

            if m in result:
                del result[m]
                if verbose:
                    print(f"   🔁 Replaced {m} → {mod.ingredient.name}")

            print(f"   🔁 Recorded replacement: {m} → {new_name}") # Debug Line

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

    # ✅ Always return consistent shape (result, changelog)
    safe_replaced = [
        e for e in replaced_entries if isinstance(e, (list, tuple)) and len(e) == 2
    ]
    return result, {
        "added": [mod.ingredient.name] if behavior == ModifierBehavior.ADD else [],
        "replaced": safe_replaced,
        "behavior": behavior,
    }
