from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from decimal import Decimal, InvalidOperation
from django.views.decorators.http import require_http_methods, require_POST
from django.db import transaction
from django.template.loader import render_to_string
from django.contrib import messages
from decimal import Decimal
import csv, io, json
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

@require_http_methods(["POST"])
def extend_recipe(request, pk):
    product = get_object_or_404(Product, pk=pk)
    source_id = request.POST.get("source_recipe_id")

    if not source_id:
        return HttpResponseBadRequest("No source recipe selected.")

    source_recipe = get_object_or_404(Product, pk=source_id)

    # Clone recipe items
    for item in RecipeItem.objects.filter(product=source_recipe):
        RecipeItem.objects.create(
            product=product,
            ingredient=item.ingredient,
            quantity=item.quantity,
            unit=item.unit,
        )

    # Return updated modal content
    recipe_items = RecipeItem.objects.filter(product=product)
    ctx = {
        "product": product,
        "recipe_items": recipe_items,
        "all_ingredients": Ingredient.objects.all(),
        "base_items": Product.objects.filter(categories__name__icontains="base"),
    }
    return render(request, "recipes/_edit_modal.html", ctx)

@require_http_methods(["GET"])
def edit_recipe_modal(request, pk):
    """
    Return the full modal for a given product (as a fragment injected by HTMX).
    """
    product = get_object_or_404(Product, pk=pk)
    context = {
        "product": product,
        "recipe_items": product.recipe_items.select_related("ingredient").all(),
        #"all_ingredients": Ingredient.objects.all().order_by("name"),
        "all_ingredients": Ingredient.objects.order_by("type", "name"),
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
    #recipe_modifiers = RecipeModifier.objects.all().order_by("type", "name") #commenting out old version
    
    base_items = Product.objects.filter(categories__name__icontains="base").order_by("name")

    # Build a dict {recipe_modifier_id: quantity} for prefill convenience (optional)
    #current_modifiers = {rm.id: rm.base_quantity for rm in recipe_modifiers} #commenting out old version

    ctx = {
        "product": product,
        "recipe_items": recipe_items,
        "all_ingredients": all_ingredients,
        "units": units,                                # e.g. [“weight”, “volume”, “count”, …]
        #"recipe_modifiers": recipe_modifiers,          # the ONLY modifier source you have
        #"current_modifiers": current_modifiers,        # {id: qty} for prefill
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
    ctx = {"products": products}

    # return render(request, "recipes/_table.html", {"products": products})
    response = render(request, "recipes/_table.html", ctx)
    response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response["Pragma"] = "no-cache"
    return response

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

        # Return rendered row so HTMX can insert it immediately
        ctx = {"item": item, "product": product}
        html = render_to_string("recipes/_edit_ingredient_row.html", ctx, request=request)
        return HttpResponse(html)

    except Exception as e:
        return JsonResponse({"error": f"Could not add ingredient: {e}"}, status=400)


@require_http_methods(["DELETE"])
@transaction.atomic
def delete_recipe_ingredient(request, product_id, item_id):
    product = get_object_or_404(Product, pk=product_id)
    item = get_object_or_404(RecipeItem, pk=item_id, product=product)
    item.delete()

    # Re-render the ingredient table body
    recipe_items = RecipeItem.objects.filter(product=product)
    ctx = {"recipe_items": recipe_items, "product": product}
    html = render_to_string("recipes/_edit_ingredient_body.html", ctx, request=request)
    return HttpResponse(html)

@require_POST
def update_recipe_item(request, pk):
    """Inline update for RecipeItem (quantity)."""
    item = get_object_or_404(RecipeItem, pk=pk)
    product = item.product

    qty = request.POST.get("quantity")
    if qty is not None:
        item.quantity = Decimal(qty)
        item.save(update_fields=["quantity"])

    return render(
        request,
        "recipes/_edit_ingredient_row.html",
        {"item": item, "product": product},  # 👈 Include product in context
    )

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

def export_recipes_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="recipes_snapshot.csv"'
    writer = csv.writer(response)
    writer.writerow(["id", "name", "category", "ingredient", "quantity"])
    for recipe in Product.objects.prefetch_related("recipe_items__ingredient").all():
        for item in recipe.recipe_items.all():
            writer.writerow([
                recipe.id,
                recipe.name,
                recipe.category.name if recipe.category else "",
                item.ingredient.name if item.ingredient else "",
                item.quantity or "",
            ])
    return response


@require_POST
def import_recipes_csv(request):
    csv_file = request.FILES.get("file")
    if not csv_file:
        messages.error(request, "⚠️ No file uploaded.")
        return redirect("recipes_dashboard")

    decoded = csv_file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))
    updated, skipped = 0, 0
    for row in reader:
        try:
            recipe = Product.objects.get(pk=row["id"])
        except Product.DoesNotExist:
            skipped += 1
            continue

        ing_name = (row.get("ingredient") or "").strip()
        if not ing_name:
            skipped += 1
            continue
        try:
            ing = Ingredient.objects.get(name__iexact=ing_name)
        except Ingredient.DoesNotExist:
            # placeholder for "unmapped items" modal in Phase 3
            skipped += 1
            continue

        qty = Decimal(row.get("quantity") or "0")
        RecipeItem.objects.update_or_create(
            product=recipe, ingredient=ing, defaults={"quantity": qty}
        )
        updated += 1

    messages.success(request, f"✅ {updated} recipe items updated, {skipped} skipped.")
    response = redirect("recipes_dashboard")
    response["HX-Trigger"] = json.dumps({"recipes:refresh": True})
    return response
