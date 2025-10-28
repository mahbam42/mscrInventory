"""
importers/_aggregate_usage.py
-----------------------------
Handles recursive expansion of RecipeModifiers and aggregation
of ingredient usage for a single product or Square import row.
"""

from decimal import Decimal
from collections import defaultdict


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


def aggregate_ingredient_usage(recipe_items, modifiers):
    """
    Given a base recipe and a set of modifiers (resolved recursively),
    aggregate the resulting ingredient usage based on each modifier's behavior.

    Returns:
        dict[str, dict]: {ingredient_name: {"qty": Decimal, "sources": [modifiers]}}
    """
    usage = defaultdict(lambda: {"qty": Decimal("0.00"), "sources": []})

    # preload base recipe
    for ri in recipe_items:
        if ri.ingredient:
            usage[ri.ingredient.name]["qty"] += ri.quantity
            usage[ri.ingredient.name]["sources"].append("base_recipe")

    # apply modifiers
    for mod in modifiers:
        behavior = mod.behavior
        q_factor = Decimal(str(mod.quantity_factor or "1.0"))
        ingredient = mod.ingredient

        # ADD behavior
        if behavior == "add" and ingredient:
            usage[ingredient.name]["qty"] += q_factor
            usage[ingredient.name]["sources"].append(mod.name)

        # REPLACE behavior
        elif behavior == "replace" and mod.replaces:
            replaces = mod.replaces or {}
            if isinstance(replaces, dict):
                targets = replaces.get("to", [])
                for mapping in targets:
                    if isinstance(mapping, list) and len(mapping) == 2:
                        new_name, factor = mapping
                        usage[new_name]["qty"] += q_factor * Decimal(str(factor))
                        usage[new_name]["sources"].append(mod.name)
            if ingredient:
                usage[ingredient.name]["sources"].append(f"{mod.name} (replace)")

        # SCALE behavior
        elif behavior == "scale" and ingredient:
            if ingredient.name in usage:
                usage[ingredient.name]["qty"] *= q_factor
                usage[ingredient.name]["sources"].append(mod.name)

        # EXPAND behavior
        elif behavior == "expand":
            for child in mod.expands_to.all():
                usage[child.name]["qty"] += q_factor
                usage[child.name]["sources"].append(mod.name)

    return dict(usage)
