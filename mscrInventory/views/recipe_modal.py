from django.shortcuts import get_object_or_404, render
from django.http import HttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.template.loader import render_to_string

from ..models import Product, Ingredient, RecipeItem, RecipeModifier


@require_http_methods(["GET"])
def edit_recipe_modal(request, pk):
    """
    Return the full modal for a given product (as a fragment injected by HTMX).
    """
    product = get_object_or_404(Product, pk=pk)
    context = {
        "product": product,
        "recipe_items": product.recipe_items.select_related("ingredient").all(),
        "all_ingredients": Ingredient.objects.all().order_by("name"),
        "all_modifiers": RecipeModifier.objects.all().order_by("type", "name"),
        "current_modifiers": list(product.modifiers.values_list("id", flat=True)) if hasattr(product, "modifiers") else [],
    }
    return render(request, "recipes/_edit_modal.html", context)


@require_http_methods(["POST"])
@transaction.atomic
def add_recipe_ingredient(request, pk):
    """
    Adds a new ingredient to a recipe (via HTMX inline form).
    """
    product = get_object_or_404(Product, pk=pk)
    try:
        ingredient_id = request.POST.get("ingredient_id")
        quantity = request.POST.get("quantity")
        unit = request.POST.get("unit") or "unit"

        if not ingredient_id or not quantity:
            return JsonResponse({"error": "Missing ingredient or quantity"}, status=400)

        ingredient = get_object_or_404(Ingredient, pk=ingredient_id)
        item = RecipeItem.objects.create(
            product=product,
            ingredient=ingredient,
            quantity=quantity,
            unit=unit,
        )

        row_html = render_to_string("recipes/_edit_ingredient_row.html", {"item": item})
        return HttpResponse(row_html)

    except Exception as e:
        return JsonResponse({"error": f"Could not add ingredient: {e}"}, status=400)


@require_http_methods(["POST"])
@transaction.atomic
def delete_recipe_ingredient(request, item_id):
    """
    Deletes a RecipeItem row and removes it from the DOM via HTMX.
    """
    try:
        item = get_object_or_404(RecipeItem, pk=item_id)
        item.delete()
        return HttpResponse(status=204)
    except Exception as e:
        return JsonResponse({"error": f"Could not delete ingredient: {e}"}, status=400)


@require_http_methods(["POST"])
@transaction.atomic
def save_recipe_modifiers(request, pk):
    """
    Save checked modifiers (checkboxes) for a product.
    """
    product = get_object_or_404(Product, pk=pk)
    try:
        selected_ids = request.POST.getlist("modifiers")
        modifiers = RecipeModifier.objects.filter(id__in=selected_ids)
        product.modifiers.set(modifiers)
        product.save(update_fields=["modified"])
        return HttpResponse(status=204)
    except Exception as e:
        return JsonResponse({"error": f"Could not save modifiers: {e}"}, status=400)
