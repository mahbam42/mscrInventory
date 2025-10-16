from django.shortcuts import get_object_or_404, render
from django.http import HttpResponse, JsonResponse
from decimal import Decimal, InvalidOperation
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.template.loader import render_to_string
from django.contrib import messages

from ..models import Product, Ingredient, RecipeItem, RecipeModifier

def recipes_dashboard_view(request):
    q = request.GET.get("category", "").strip()
    products = Product.objects.all().order_by("name")

    # Treat 'none' (or similar) as no filter
    if q.lower() in ("none", "null"):
        q = ""
        products = Product.objects.all().order_by("name")

    if q:
        # accept either an ID (e.g. "12") or a name (e.g. "Espresso Drinks")
        if q.isdigit():
            products = products.filter(categories__id=int(q))
        else:
            products = products.filter(categories__name=q)

    # Build a list of available categories from the related M2M
    categories = (
        Product.objects
        .values("categories__id", "categories__name")
        .distinct()
        .order_by("categories__name")
    )

    base_items = (
    Product.objects
    .filter(categories__name__iexact="Base Item")
    .order_by("name")
)

    ctx = {
        "products": products,
        "categories": categories,   # list of dicts with keys categories__id / categories__name
        "selected_category": q,
        "base_items": base_items,
    }
    return render(request, "recipes/dashboard.html", ctx)

def extend_recipe(request, pk):
    """
    Extend a product's recipe using another product marked as a 'Base Item' category.
    """
    product = get_object_or_404(Product, pk=pk)
    source_id = request.POST.get("source_recipe_id")

    if not source_id:
        return JsonResponse({"error": "No base item selected."}, status=400)

    source_product = get_object_or_404(
        Product, pk=source_id, categories__name__iexact="Base Item"
    )

    # Copy ingredients
    for item in RecipeItem.objects.filter(product=source_product):
        RecipeItem.objects.create(
            product=product,
            ingredient=item.ingredient,
            quantity=item.quantity,
            unit=item.unit,
        )

    # Copy modifiers (optional)
    for mod in RecipeModifier.objects.filter(product=source_product):
        RecipeModifier.objects.create(
            name=mod.name,
            ingredient=mod.ingredient,
            base_quantity=mod.base_quantity,
            unit=mod.unit,
            size_multiplier=mod.size_multiplier,
            type=mod.type,
        )

    messages.success(request, f"Copied ingredients from base recipe: {source_product.name}")
    return HttpResponse(status=204)

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

@require_http_methods(["GET"])
def edit_recipe_view(request, pk):
    product = get_object_or_404(Product, pk=pk)

    # existing ingredients on this recipe
    recipe_items = (
        RecipeItem.objects
        .filter(product=product)
        .select_related("ingredient", "product")
        .order_by("ingredient__name")
    )

    # all ingredients for selector, grouped by unit_type then name
    all_ingredients = Ingredient.objects.all().order_by("type", "name")

    # distinct unit “types” (since your model has unit_type, not type/unit)
    units = (
        Ingredient.objects
        .values_list("unit_type", flat=True)
        .distinct()
        .order_by("unit_type")
    )

    # existing modifiers FOR THIS PRODUCT (since there is no base Modifier model)
    recipe_modifiers = RecipeModifier.objects.all().order_by("type", "name")
    
    base_items = Product.objects.filter(categories__name__iexact="Base Item").order_by("name")

    # Build a dict {recipe_modifier_id: quantity} for prefill convenience (optional)
    current_modifiers = {rm.id: rm.base_quantity for rm in recipe_modifiers}

    ctx = {
        "product": product,
        "recipe_items": recipe_items,
        "all_ingredients": all_ingredients,
        "units": units,                                # e.g. [“weight”, “volume”, “count”, …]
        "recipe_modifiers": recipe_modifiers,          # the ONLY modifier source you have
        "current_modifiers": current_modifiers,        # {id: qty} for prefill
        "base_items": base_items,
    }
    return render(request, "recipes/_edit_modal.html", ctx)

def recipes_table_fragment(request):
    q = request.GET.get("category", "").strip()
    products = Product.objects.all().order_by("name")

    if q:
        if q.isdigit():
            products = products.filter(categories__id=int(q))
        else:
            products = products.filter(categories__name=q)

    return render(request, "recipes/_table.html", {"products": products})

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
            quantity=Decimal(quantity),
            unit=unit,
        )

        # render just the row fragment
        row_html = render_to_string("recipes/_edit_ingredient_row.html", {"item": item}, request=request)
        return HttpResponse(row_html)

    except Exception as e:
        return JsonResponse({"error": f"Could not add ingredient: {e}"}, status=400)


@require_http_methods(["DELETE"])
@transaction.atomic
def delete_recipe_ingredient(request, product_id, item_id):
    """
    Deletes a RecipeItem row and removes it from the DOM via HTMX.
    """
    item = get_object_or_404(RecipeItem, pk=item_id, product_id=product_id)
    item.delete()
    return HttpResponse(status=204)

@require_http_methods(["POST"])
@transaction.atomic
def save_recipe_modifiers(request, pk):
    # TODO: implement per-recipe modifier mapping later
    """product = get_object_or_404(Product, pk=pk)
    for rm in RecipeModifier.objects.filter(product=product):
        key = f"modifier_qty_{rm.id}"
        if key in request.POST:
            raw = (request.POST.get(key) or "").strip()
            try:
                rm.quantity = Decimal(raw or "0")
            except (InvalidOperation, TypeError):
                rm.quantity = Decimal("0")
            rm.save(update_fields=["quantity"])
    return HttpResponse(status=204) """

""" commenting out old version
def save_recipe_modifiers(request, pk):
    product = get_object_or_404(Product, pk=pk)
    try:
        selected_ids = request.POST.getlist("modifiers")
        modifiers = RecipeModifier.objects.filter(id__in=selected_ids)
        product.modifiers.set(modifiers)
        product.save(update_fields=["modified"])
        return HttpResponse(status=204)
    except Exception as e:
        return JsonResponse({"error": f"Could not save modifiers: {e}"}, status=400) """
