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
from typing import Dict, List, Optional, Iterable, Tuple
from mscrInventory.models import Ingredient, RecipeModifier, RecipeModifierAlias, RecipeItem, ModifierBehavior, Product
import logging
import re

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
    token = re.sub(r"[^a-z0-9\s]", " ", token)
    token = re.sub(r"\s+", " ", token)
    return token.strip()


CATERING_PACKAGE_TOKEN = normalize_modifier(
    "Accommodating Packages: Beverage for 10 people. Dairy or Non Dairy 3 x 10oz bottles per 96 oz Box. "
    "10 pack of Cups included. 20 assorted packs of sweetener included. Stirrers and Napkins included."
)
CATERING_PACKAGE_ITEMS = [
    ("To Go Bottle", Decimal("3")),
]
CATERING_PACKAGE_MILKS = [
    ("Whole Milk", Decimal("10")),
    ("Oat Milk", Decimal("10")),
    ("Almond Milk", Decimal("10")),
]


def _select_targets(recipe_map: Dict[str, Dict],
                    current_context: Optional[List[str]] = None,
                    by_type: Optional[Iterable[object]] = None,
                    by_name: Optional[Iterable[str]] = None) -> List[str]:
    """Restrict matches to ingredients within the current recipe context."""
    if current_context:
        recipe_map = {k: v for k, v in recipe_map.items() if k in current_context}
    by_type_ids: set[int] = set()
    by_type_names: set[str] = set()
    for value in by_type or []:
        if value is None:
            continue
        if isinstance(value, int):
            by_type_ids.add(value)
            continue
        if isinstance(value, str):
            if value.isdigit():
                try:
                    by_type_ids.add(int(value))
                    continue
                except ValueError:
                    pass
            by_type_names.add(value.strip().lower())
            continue
    by_type_names = {name for name in by_type_names if name}
    by_name = {_normalize_token(n) for n in (by_name or [])}
    matches = []
    for ing_name, meta in recipe_map.items():
        ing_type_name = (meta.get("type_name") or meta.get("type") or "").strip().lower()
        ing_type_id = meta.get("type_id")
        type_match = False
        if by_type_ids and ing_type_id is not None:
            type_match = ing_type_id in by_type_ids
        if not type_match and by_type_names:
            type_match = ing_type_name in by_type_names
        if (by_type_ids or by_type_names) and type_match:
            matches.append(ing_name)
            continue
        if _normalize_token(ing_name) in by_name:
            matches.append(ing_name)
    return matches


def _lookup_modifier_or_recipe(name: str) -> Optional[object]:
    """Return a matching RecipeModifier, Product, or RecipeItem."""
    """Try to resolve a name to a RecipeModifier or Product/RecipeItem."""
    if not name:
        return None
    name_norm = _normalize_token(name)
    alias_norm = normalize_modifier(name)
    alias_tokens = [alias_norm, name_norm]
    for token in alias_tokens:
        if not token:
            continue
        alias = RecipeModifierAlias.objects.select_related('modifier').filter(normalized_label=token).first()
        if alias:
            return alias.modifier
    alias = RecipeModifierAlias.objects.select_related('modifier').filter(raw_label__iexact=name).first()
    if alias:
        return alias.modifier
    candidates = [name, name_norm]
    for token in candidates:
        mod = RecipeModifier.objects.filter(name__iexact=token).first()
        if mod:
            return mod
        mod = RecipeModifier.objects.filter(name__icontains=token).first()
        if mod:
            return mod
    # 1) Barista's Choice product recipes (named drinks)
    barista_category_filter = {"categories__name__icontains": "barista"}
    product_qs = Product.objects.filter(**barista_category_filter).prefetch_related(
        "recipe_items__ingredient",
        "recipe_items__ingredient__type",
        "categories",
    )

    # Prefer exact-ish matches, then fall back to partials.
    product = product_qs.filter(name__iexact=name).first()
    if not product and name != name_norm:
        product = product_qs.filter(name__iexact=name_norm).first()
    if not product:
        product = product_qs.filter(name__icontains=name).order_by("name").first()
    if not product and name != name_norm:
        product = product_qs.filter(name__icontains=name_norm).order_by("name").first()
    if product:
        return product

    recipe_item = RecipeItem.objects.filter(
        ingredient__name__icontains=name_norm
    ).select_related("ingredient", "product").first()
    if recipe_item:
        return recipe_item
    return None


def _inject_recipe_ingredient(recipe_map: Dict[str, Dict], ingredient_name: str, quantity: Decimal) -> Optional[str]:
    """
    Ensure the given ingredient exists in recipe_map, incrementing quantity when already present.
    Returns the canonical ingredient name when successful.
    """
    ingredient = (
        Ingredient.objects.select_related("type")
        .filter(name__iexact=ingredient_name)
        .first()
    )
    if not ingredient:
        return None

    qty = Decimal(str(quantity))
    entry = recipe_map.get(ingredient.name)
    if entry:
        current = Decimal(str(entry.get("qty", "0") or "0"))
        entry["qty"] = current + qty
        return ingredient.name

    ing_type = getattr(ingredient, "type", None)
    recipe_map[ingredient.name] = {
        "qty": qty,
        "type_id": getattr(ing_type, "id", None),
        "type_name": getattr(ing_type, "name", "") or "",
        "type": getattr(ing_type, "name", "") or "",
    }
    return ingredient.name


def _apply_catering_package_bundle(recipe_map: Dict[str, Dict]):
    """Custom expansion for the catering bundles present in Square data."""
    additions: List[str] = []
    for name, qty in CATERING_PACKAGE_ITEMS + CATERING_PACKAGE_MILKS:
        added = _inject_recipe_ingredient(recipe_map, name, qty)
        if added:
            additions.append(added)
    return recipe_map, {
        "added": additions,
        "replaced": [],
        "behavior": "catering_box_bundle",
    }


# -----------------------------------------------------------------------
# Helper: Expand a Barista’s Choice Product recipe into the current context
# -----------------------------------------------------------------------

def _expand_baristas_choice(
    product: Product,
    recipe_map: Dict[str, Dict],
    verbose: bool = False,
):
    """Merge a Barista's Choice recipe into the working recipe map."""
    added: List[str] = []
    overridden: List[Tuple[str, str]] = []
    for item in product.recipe_items.all():
        ing = item.ingredient
        ing_name = ing.name
        ing_type = ing.type
        qty = Decimal(item.quantity or 1)
        existed = ing_name in recipe_map
        recipe_map[ing_name] = {
            "qty": qty,
            "type_id": getattr(ing_type, "id", None),
            "type_name": getattr(ing_type, "name", "") or "",
            "type": getattr(ing_type, "name", "") or "",
        }
        if verbose:
            status = "🔁 override" if existed else "➕ add"
            print(f"   {status}: {ing_name} ×{qty} (from {product.name})")
        if existed:
            overridden.append((ing_name, ing_name))
        added.append(ing_name)
    if verbose:
        print(f"🧩 Expanded from Barista's Choice recipe: {product.name}")
    return recipe_map, {
        "added": added,
        "replaced": overridden,
        "behavior": "expand_baristas_choice",
        "source_recipe": product.name,
    }


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def handle_extras(
    modifier_name: str,
    recipe_map: Dict[str, Dict],
    normalized_modifiers: List[str],
    recipe_context: Optional[List[str]] = None,
    verbose: bool = False,
):
    """Expand, scale, or replace ingredients based on modifier-specific rules."""
    result = recipe_map.copy()
    normalized_label = normalize_modifier(modifier_name)
    if normalized_label == CATERING_PACKAGE_TOKEN:
        return _apply_catering_package_bundle(result)
    name_norm = _normalize_token(modifier_name)

    target = _lookup_modifier_or_recipe(modifier_name)
    if not target:
        IGNORED_TOKENS = {"iced", "ice", "hot", "small", "medium", "large", "xl"}
        if name_norm in IGNORED_TOKENS:
            if verbose:
                print(f"🧊 Ignored size/temp token '{modifier_name}'")
            return result, {"added": [], "replaced": [], "behavior": "ignored_variant"}
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
            type_obj = item.ingredient.type
            result[item.ingredient.name] = {
                "qty": item.quantity,
                "type_id": getattr(type_obj, "id", None),
                "type_name": getattr(type_obj, "name", "") or "",
                "type": getattr(type_obj, "name", "") or "",
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
    if not isinstance(sel, dict):
        sel = {}
    by_type = sel.get("by_type", [])
    by_name = sel.get("by_name", [])

    matched = _select_targets(result, recipe_context, by_type, by_name)
    replaced_entries = []

    ingredient = getattr(mod, "ingredient", None)
    ingredient_name = getattr(ingredient, "name", mod.name)
    ingredient_type = getattr(ingredient, "type", None)
    ingredient_type_name = getattr(ingredient_type, "name", None) or getattr(getattr(mod, "ingredient_type", None), "name", "")
    ingredient_type_id = (
        getattr(ingredient_type, "id", None)
        if ingredient_type is not None
        else getattr(mod, "ingredient_type_id", None)
    )
    ingredient_type_name = ingredient_type_name or ""

    if verbose:
        print(f"🧩 Modifier: {modifier_name} ({behavior})")
        print(f"   → Matches in context: {matched or 'none'}")

    # --- ADD ---------------------------------------------------------------
    if behavior == ModifierBehavior.ADD:
        result[ingredient_name] = {
            "qty": getattr(mod, "base_quantity", Decimal("1.0")),
            "type_id": ingredient_type_id,
            "type_name": ingredient_type_name,
            "type": ingredient_type_name,
        }
        if verbose:
            print(f"   ➕ Added {ingredient_name} ×{getattr(mod, 'base_quantity', Decimal('1.0'))}")

    # --- REPLACE -----------------------------------------------------------
    elif behavior == ModifierBehavior.REPLACE:
        new_name = ingredient_name
        for m in matched or []:
            if m in result:
                del result[m]
                if verbose:
                    print(f"   🔁 Replaced {m} → {new_name}")
            replaced_entries.append((m, new_name))
        result[new_name] = {
            "qty": getattr(mod, "base_quantity", Decimal("1.0")),
            "type_id": ingredient_type_id,
            "type_name": ingredient_type_name,
            "type": ingredient_type_name,
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
        sub_type = sub_ing.type
        sub_qty = getattr(sub, "base_quantity", Decimal("1.0"))
        result[sub_name] = {
            "qty": sub_qty,
            "type_id": getattr(sub_type, "id", None),
            "type_name": getattr(sub_type, "name", "") or "",
            "type": getattr(sub_type, "name", "") or "",
        }
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
