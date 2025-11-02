# mscrInventory/views.py
from django.shortcuts import render

from mscrInventory.views.imports import _build_unmapped_context
from .models import Ingredient

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
    items = Ingredient.objects.filter(name__startswith="Unmapped:").order_by("name")
    context = {"items": items, "type": "ingredient"}
    return render(request, "partials/unmapped_ingredients_table.html", context)


def empty_modal_partial(request):
    """Fallback content for the shared modal."""
    return render(request, "partials/empty_modal.html")
