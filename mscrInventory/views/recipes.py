# mscrInventory/views/recipes.py

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods, require_POST
from django.db import transaction, models
from django.views.decorators.csrf import csrf_protect
from mscrInventory.models import Product, RecipeItem, Ingredient, RecipeModifier
from decimal import Decimal


def recipes_dashboard_view(request):
    products = Product.objects.prefetch_related("categories", "recipe_items").order_by("name")
    total_products = products.count()
    products_without_recipes = products.filter(recipe_items__isnull=True).count()
    total_modifiers = RecipeModifier.objects.count()

    context = {
        "products": products,
        "total_products": total_products,
        "products_without_recipes": products_without_recipes,
        "total_modifiers": total_modifiers,
    }
    return render(request, "recipes/dashboard.html", context)
@csrf_protect
def edit_recipe_view(request, product_id):
    product = get_object_or_404(Product, pk=product_id)

    if request.method == "POST":
        try:
            with transaction.atomic():
                # --- INGREDIENTS ---
                # Clear out old ingredients
                RecipeItem.objects.filter(product=product).delete()

                # Expect ingredient fields like ingredients-0-id, ingredients-0-quantity, ...
                # Collect all indexes from POST keys
                ingredient_rows = {}
                for key, value in request.POST.items():
                    if key.startswith("ingredients-") and "-" in key:
                        _, idx, field = key.split("-", 2)
                        ingredient_rows.setdefault(idx, {})[field] = value

                for row in ingredient_rows.values():
                    ing_id = row.get("id")
                    quantity = row.get("quantity")
                    unit = row.get("unit")
                    if not ing_id or not quantity:
                        continue  # skip blank rows
                    ingredient = Ingredient.objects.get(pk=ing_id)
                    RecipeItem.objects.create(
                        product=product,
                        ingredient=ingredient,
                        quantity=quantity,
                        unit=unit,
                    )

                # --- MODIFIERS ---
                # Modifiers can be a list of ids (checkboxes)
                modifier_ids = request.POST.getlist("modifiers")
                modifiers = RecipeModifier.objects.filter(id__in=modifier_ids)
                product.modifiers.set(modifiers)

        except Exception as e:
            return HttpResponseBadRequest(f"Error saving recipe: {e}")

        # Return updated modal body so htmx can replace it
        return render(request, "recipes/edit_recipe_modal.html", {"product": product})

    # GET: load the modal as before
    context = {
        "product": product,
        "ingredients": RecipeItem.objects.filter(product=product),
        "modifiers": RecipeModifier.objects.all(),
    }
    return render(request, "recipes/edit_recipe_modal.html", context)
# @require_http_methods(["GET", "POST"])
# def edit_recipe_view(request, product_id):
#     product = get_object_or_404(Product, pk=product_id)

#     if request.method == "POST":
#         try:
#             with transaction.atomic():
#                 # Clear existing
#                 RecipeItem.objects.filter(product=product).delete()
#                 product.modifiers.clear()

#                 # Collect all row suffixes seen in the POST (robust even with gaps)
#                 suffixes = set()
#                 for k in request.POST.keys():
#                     if k.startswith("ingredient_name_") or k.startswith("ingredient_id_"):
#                         suffixes.add(k.rsplit("_", 1)[1])

#                 for idx in sorted(suffixes, key=lambda s: int(s)):
#                     name = (request.POST.get(f"ingredient_name_{idx}") or "").strip()
#                     ing_id = (request.POST.get(f"ingredient_id_{idx}") or "").strip()
#                     qty_s = (request.POST.get(f"quantity_{idx}") or "").strip()
#                     unit = (request.POST.get(f"unit_{idx}") or "").strip()
#                     cost_s = (request.POST.get(f"cost_{idx}") or "").strip()
#                     price_s = (request.POST.get(f"price_{idx}") or "").strip()

#                     # skip truly empty rows
#                     if not name and not ing_id:
#                         continue

#                     if ing_id:
#                         ingredient = Ingredient.objects.get(pk=ing_id)
#                     else:
#                         if not name:
#                             continue
#                         ingredient, _ = Ingredient.objects.get_or_create(name=name)

#                     def to_dec(s, default="0"):
#                         try:
#                             return Decimal(s or default)
#                         except (InvalidOperation, TypeError):
#                             return Decimal(default)

#                     qty = to_dec(qty_s)
#                     cost = to_dec(cost_s)
#                     price = to_dec(price_s)
#                     final_unit = unit or ingredient.unit_type

#                     RecipeItem.objects.create(
#                         product=product,
#                         ingredient=ingredient,
#                         quantity=qty,
#                         unit=final_unit,
#                         cost_per_unit=cost,
#                         price_per_unit=price,
#                     )

#                 # Modifiers (checkbox group named "modifiers")
#                 mod_ids = request.POST.getlist("modifiers")
#                 if mod_ids:
#                     product.modifiers.set(RecipeModifier.objects.filter(id__in=mod_ids))

#             # Close modal & refresh (simple)
#             return HttpResponse('<script>window.location.reload();</script>')

#         except Exception as e:
#             return JsonResponse({"error": str(e)}, status=400)

#     # GET (unchanged): render modal with existing data
#     ingredients = RecipeItem.objects.filter(product=product).select_related("ingredient")
#     modifiers_by_type = {}
#     for m in RecipeModifier.objects.all().select_related("ingredient"):
#         modifiers_by_type.setdefault(m.type, []).append(m)
#     current_modifiers = set(product.modifiers.values_list("id", flat=True))

#     return render(request, "recipes/_edit_modal.html", {
#         "product": product,
#         "ingredients": ingredients,
#         "modifiers_by_type": modifiers_by_type,
#         "current_modifiers": current_modifiers,
#     })

@require_POST
def add_recipe_ingredient_view(request, product_id):
    """
    Adds a blank RecipeItem row to the modal table dynamically via HTMX.
    """
    product = get_object_or_404(Product, pk=product_id)

    # Create a blank RecipeItem (you can also just render a blank form row if you prefer)
    ingredient_id = request.POST.get("ingredient_id")
    quantity = request.POST.get("quantity", "0")
    unit = request.POST.get("unit", "unit")

    if not ingredient_id:
        return HttpResponseBadRequest("Missing ingredient_id")

    ingredient = get_object_or_404(Ingredient, pk=ingredient_id)

    with transaction.atomic():
        recipe_item = RecipeItem.objects.create(
            product=product,
            ingredient=ingredient,
            quantity=quantity,
            unit=unit,
        )

    # Return the rendered HTML for this single new row
    return render(
        request,
        "recipes/partials/recipe_ingredient_row.html",
        {"item": recipe_item},
    )


@require_POST
def delete_recipe_ingredient_view(request, ingredient_id):
    """
    Deletes a RecipeItem from the recipe table dynamically via HTMX.
    """
    try:
        recipe_item = RecipeItem.objects.get(pk=ingredient_id)
    except RecipeItem.DoesNotExist:
        return HttpResponseBadRequest("RecipeItem not found")

    with transaction.atomic():
        recipe_item.delete()

    # Returning a 204 tells HTMX to remove the row without re-rendering
    return HttpResponse(status=204)
@require_POST
def save_recipe_view(request, product_id):
    product = get_object_or_404(Product, pk=product_id)

    # --- Update modifiers ---
    selected_mod_ids = request.POST.getlist("modifiers")
    product.modifiers.set(selected_mod_ids)

    # --- Update base ingredients ---
    for key, value in request.POST.items():
        if key.startswith("base_") and key.endswith("_quantity"):
            item_id = key.split("_")[1]
            try:
                item = RecipeItem.objects.get(id=item_id, product=product)
                item.quantity = value or 0
                item.save()
            except RecipeItem.DoesNotExist:
                # Later we can handle adding new ingredients
                pass

    return HttpResponse(
        "<div class='p-3'>✅ Recipe saved successfully!</div>"
    )
