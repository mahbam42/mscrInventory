# mscrInventory/views.py
from django.shortcuts import render
from .models import Product, Ingredient, SquareUnmappedItem

# --------------------------------------------------------------------
# Unified HTMX partials for unmapped items
# --------------------------------------------------------------------

def unmapped_products_partial(request):
    """
    Partial table for unmapped products.
    Appears on Products dashboard and Imports dashboard.
    """
    square_items = SquareUnmappedItem.objects.all()
    legacy_products = Product.objects.filter(name__startswith="Unmapped:").order_by("name")
    context = {
        "square_items": square_items,
        "legacy_products": legacy_products,
    }
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
