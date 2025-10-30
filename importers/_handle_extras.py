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
    """Normalize a raw Square modifier string for matching."""
    if not raw:
        return ""
    token = raw.strip().lower()
    token = token.replace("½", "half").replace("1/2", "half")
    token = token.replace("-", " ").replace("_", " ")
    token = token.replace("’", "'").replace("–", "-")
    while "  " in token:
        token = token.replace("  ", " ")
    return token


def _select_targets(recipe_map: Dict[str, Dict],
                    current_context: Optional[List[str]] = None,
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

    # don't know if this will help
    # 3) Barista’s Choice product recipes
    product = Product.objects.filter(
        name__iexact=name_norm,
        categories__name__iexact="Barista's Choice"
    ).prefetch_related("recipe_items__ingredient", "categories").first()
    if product:
        return product
    if recipe_item:
        return recipe_item
    return None


# -----------------------------------------------------------------------
# Helper: Expand a Barista’s Choice Product recipe into the current context
# -----------------------------------------------------------------------

def _expand_baristas_choice(product: Product,
                            recipe_map: Dict[str, Dict],
                            verbose: bool = False):
    """
    Merge the given Barista's Choice product recipe_items into the current recipe_map.
    - Overrides duplicate ingredient quantities instead of adding.
    - Does not replace the base recipe.
    """
    added = []
    overridden = []
    for item in product.recipe_items.all():
        ing = item.ingredient
        ing_name = ing.name
        ing_type = ing.type.name if getattr(ing, "type", None) else ""
        qty = Decimal(item.quantity or 1)
        if ing_name in recipe_map:
            overridden.append(ing_name)
        recipe_map[ing_name] = {"qty": qty, "type": ing_type}
        if verbose:
            status = "🔁 override" if ing_name in overridden else "➕ add"
            print(f"   {status}: {ing_name} ×{qty} (from {product.name})")
        added.append(ing_name)
    if verbose:
        print(f"🧩 Expanded from Barista's Choice recipe: {product.name}")
    return recipe_map, {
        "added": added,
        "replaced": [(n, n) for n in overridden],
        "behavior": "expand_baristas_choice",
        "source_recipe": product.name,
    }


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

    # --- Ignore known size/temp tokens ------------------------------------
    IGNORED_TOKENS = {"iced", "ice", "hot", "small", "medium", "large", "xl"}
    if name_norm in IGNORED_TOKENS:
        if verbose:
            print(f"🧊 Ignored size/temp token '{modifier_name}'")
        return result, {"added": [], "replaced": [], "behavior": "ignored_variant"}

    target = _lookup_modifier_or_recipe(modifier_name)
    if not target:
        if verbose:
            print(f"⚠️  No modifier or recipe found for '{modifier_name}'")
        return result, {"added": [], "replaced": [], "behavior": None}

    # -----------------------------------------------------------------------
    # Case 1: Modifier is actually a recipe (e.g., Cherry Dipped Vanilla)
    # -----------------------------------------------------------------------
    if isinstance(target, RecipeItem):
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
        }

    # -----------------------------------------------------------------------
    # Case 1b: Modifier matches a Barista’s Choice product recipe
    # -----------------------------------------------------------------------
    if isinstance(target, Product) and any(
        "barista" in (c.name or "").lower() for c in target.categories.all()
    ):
        if verbose:
            print(f"🧩 Modifier: {modifier_name} recognized as Barista’s Choice recipe")
        return _expand_baristas_choice(target, result, verbose)

    # -----------------------------------------------------------------------
    # Case 2: Modifier is a RecipeModifier
    # -----------------------------------------------------------------------
    if not isinstance(target, RecipeModifier):
        if verbose:
            print(f"⚠️  Skipping '{modifier_name}' (not a valid RecipeModifier)")
        return result, {"added": [], "replaced": [], "behavior": None}

    mod = target
    behavior = getattr(mod, "behavior", ModifierBehavior.ADD)
    quantity_factor = getattr(mod, "quantity_factor", Decimal("1.0"))
    sel = getattr(mod, "target_selector", {}) or {}
    by_type = sel.get("by_type", [])
    by_name = sel.get("by_name", [])

    matched = _select_targets(result, recipe_context, by_type, by_name)
    replaced_entries = []

    ingredient = getattr(mod, "ingredient", None)
    ingredient_name = getattr(ingredient, "name", mod.name)
    ingredient_type = getattr(getattr(ingredient, "type", None), "name", mod.type)

    if verbose:
        print(f"🧩 Modifier: {modifier_name} ({behavior})")
        print(f"   → Matches in context: {matched or 'none'}")

    # --- ADD ---------------------------------------------------------------
    if behavior == ModifierBehavior.ADD:
        result[ingredient_name] = {
            "qty": getattr(mod, "base_quantity", Decimal("1.0")),
            "type": ingredient_type,
        }
        if verbose:
            print(f"   ➕ Added {ingredient_name} ×{getattr(mod, 'base_quantity', Decimal('1.0'))}")

    # --- REPLACE -----------------------------------------------------------
    elif behavior == ModifierBehavior.REPLACE:
        for m in matched or []:
            new_name = ingredient_name
            if m in result:
                del result[m]
                if verbose:
                    print(f"   🔁 Replaced {m} → {new_name}")
            replaced_entries.append((m, new_name))
        result[new_name] = {
            "qty": getattr(mod, "base_quantity", Decimal("1.0")),
            "type": ingredient_type,
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
        sub_ing = getattr(sub, "ingredient", None)
        if not sub_ing:
            continue
        sub_name = sub_ing.name
        sub_type = sub_ing.type.name if getattr(sub_ing, "type", None) else ""
        sub_qty = getattr(sub, "base_quantity", Decimal("1.0"))
        result[sub_name] = {"qty": sub_qty, "type": sub_type}
        if verbose:
            print(f"   🌱 Expanded to include {sub_name}")

    # ✅ Always return consistent shape (result, changelog)
    safe_replaced = [
        e for e in replaced_entries if isinstance(e, (list, tuple)) and len(e) == 2
    ]
    return result, {
        "added": [ingredient_name] if behavior == ModifierBehavior.ADD else [],
        "replaced": safe_replaced,
        "behavior": behavior,
    }
