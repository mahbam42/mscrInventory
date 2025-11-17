"""Thin wrappers that share HTMX partials across dashboards."""
from django.shortcuts import render

from mscrInventory.views.imports import _build_unmapped_context

# --------------------------------------------------------------------
# Unified HTMX partials for unmapped items
# --------------------------------------------------------------------

def unmapped_products_partial(request):
    """
    Partial table for unmapped products.
    Appears on Products dashboard and Imports dashboard.
    """
    context = _build_unmapped_context(filter_type="product")
    return render(request, "partials/unmapped_square_items_table.html", context)


def unmapped_ingredients_partial(request):
    """
    Partial table for unmapped ingredients.
    Appears on Recipes dashboard and Imports dashboard.
    """
    context = _build_unmapped_context(filter_type="ingredient")
    type_data = context.get("unmapped_by_type", {}).get(
        "ingredient", {"items": [], "label": "Ingredient", "total": 0}
    )
    return render(
        request,
        "imports/_unmapped_type_table.html",
        {"type_key": "ingredient", "type_data": type_data, "include_known": False},
    )


def unmapped_modifiers_partial(request):
    """
    Partial table for unmapped modifiers.
    Mirrors the ingredient block for dashboards.
    """

    context = _build_unmapped_context(filter_type="modifier")
    type_data = context.get("unmapped_by_type", {}).get(
        "modifier", {"items": [], "label": "Modifier", "total": 0}
    )
    return render(
        request,
        "imports/_unmapped_type_table.html",
        {"type_key": "modifier", "type_data": type_data, "include_known": False},
    )


def empty_modal_partial(request):
    """Fallback content for the shared modal."""
    return render(request, "partials/empty_modal.html")
