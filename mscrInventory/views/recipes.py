# mscrInventory/views/recipes.py

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.db import transaction, models
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

@require_http_methods(["GET", "POST"])
def edit_recipe_view(request, product_id):
    product = get_object_or_404(Product, pk=product_id)

    if request.method == "POST":
        try:
            with transaction.atomic():
                # 1️⃣ Delete existing recipe items & modifiers
                RecipeItem.objects.filter(product=product).delete()
                product.modifiers.clear()

                # 2️⃣ Recreate recipe items from form data
                index = 0
                while True:
                    ingredient_name = request.POST.get(f"ingredient_name_{index}")
                    ingredient_id = request.POST.get(f"ingredient_id_{index}")
                    quantity = request.POST.get(f"quantity_{index}")
                    unit = request.POST.get(f"unit_{index}")
                    cost = request.POST.get(f"cost_{index}")
                    price = request.POST.get(f"price_{index}")

                    if not ingredient_name and not ingredient_id:
                        break  # stop once we run out of rows

                    # Find or create ingredient by name
                    if ingredient_id:
                        ingredient = Ingredient.objects.get(pk=ingredient_id)
                    else:
                        ingredient, _ = Ingredient.objects.get_or_create(name=ingredient_name.strip())

                    RecipeItem.objects.create(
                        product=product,
                        ingredient=ingredient,
                        quantity=Decimal(quantity or "0"),
                        unit=unit or ingredient.unit_type,
                        cost_per_unit=Decimal(cost or "0"),
                        price_per_unit=Decimal(price or "0"),
                    )

                    index += 1

                # 3️⃣ Save modifiers (checkboxes)
                modifier_ids = request.POST.getlist("modifiers")
                if modifier_ids:
                    modifiers = RecipeModifier.objects.filter(id__in=modifier_ids)
                    product.modifiers.set(modifiers)

            # Return a partial update to close modal and maybe refresh the row
            return HttpResponse(
                '<script>window.location.reload();</script>'
            )

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=400)

    # GET behavior stays the same (already implemented)
    ingredients = RecipeItem.objects.filter(product=product).select_related("ingredient")

    modifiers_by_type = {}
    for modifier in RecipeModifier.objects.all().select_related("ingredient"):
        modifiers_by_type.setdefault(modifier.type, []).append(modifier)

    current_modifiers = set(product.modifiers.all().values_list("id", flat=True))

    context = {
        "product": product,
        "ingredients": ingredients,
        "modifiers_by_type": modifiers_by_type,
        "current_modifiers": current_modifiers,
    }
    return render(request, "recipes/_edit_modal.html", context)
# older code
# @require_http_methods(["GET", "POST"])
# def edit_recipe_view(request, product_id):
#     product = get_object_or_404(Product, pk=product_id)

#     if request.method == "POST":
#         try:
#             with transaction.atomic():
#                 # --- 1️⃣ Update ingredient quantities ---
#                 for key, value in request.POST.items():
#                     if key.startswith("quantity_") and value.strip() != "":
#                         item_id = key.split("_", 1)[1]
#                         try:
#                             item = RecipeItem.objects.get(pk=item_id, product=product)
#                             new_qty = Decimal(value)
#                             if new_qty != item.quantity:
#                                 item.quantity = new_qty
#                                 item.save(update_fields=["quantity"])
#                         except RecipeItem.DoesNotExist:
#                             pass  # could also log this if needed

#                 # --- 2️⃣ Update modifier selections ---
#                 # Clear existing modifiers
#                 product.recipemodifier_set.clear()

#                 # Re-add checked modifiers
#                 selected_mod_ids = [
#                     key.split("_", 1)[1]
#                     for key in request.POST.keys()
#                     if key.startswith("modifier_")
#                 ]
#                 if selected_mod_ids:
#                     mods = RecipeModifier.objects.filter(id__in=selected_mod_ids)
#                     # Assuming many-to-many between Product and RecipeModifier (if not, see note below)
#                     product.recipemodifier_set.add(*mods)

#             return JsonResponse({"success": True, "message": "Recipe updated successfully."})
#         except Exception as e:
#             return JsonResponse({"success": False, "message": str(e)}, status=400)

#     # --- GET method: render modal ---
#     recipe_items = RecipeItem.objects.filter(product=product).select_related("ingredient")
#     modifiers = models.ManyToManyField("RecipeModifier", blank=True, related_name="products")
#     # modifiers = RecipeModifier.objects.all().order_by("type", "name")
#     selected_modifiers = product.recipemodifier_set.values_list("id", flat=True)

#     context = {
#         "product": product,
#         "recipe_items": recipe_items,
#         "modifiers": modifiers,
#         "selected_modifiers": set(selected_modifiers),
#     }
#     return render(request, "recipes/_edit_modal.html", context)

# def edit_recipe_view(request, product_id):
#     """
#     Loads the recipe editor modal for a given product.
#     """
#     product = get_object_or_404(Product, pk=product_id)

#     if request.method == "GET":
#         # Load existing ingredients
#         ingredients = RecipeItem.objects.filter(product=product).select_related("ingredient")

#         # Load modifiers, grouped by type for UI clarity
#         modifiers_by_type = {}
#         for modifier in RecipeModifier.objects.all().select_related("ingredient"):
#             modifiers_by_type.setdefault(modifier.type, []).append(modifier)

#         # Pre-select the product's current modifiers
#         current_modifiers = set(product.modifiers.all().values_list("id", flat=True))

#         context = {
#             "product": product,
#             "ingredients": ingredients,
#             "modifiers_by_type": modifiers_by_type,
#             "current_modifiers": current_modifiers,
#         }
#         return render(request, "recipes/_edit_modal.html", context)
# def edit_recipe_view(request, product_id):
#     product = get_object_or_404(Product, pk=product_id)
#     base_items = product.recipe_items.select_related("ingredient")
#     all_modifiers = RecipeModifier.objects.all().order_by("type", "name")
#     product_modifiers = product.modifiers.all()

#     return render(
#         request,
#         "recipes/edit_recipe_modal.html",
#         {
#             "product": product,
#             "base_items": base_items,
#             "all_modifiers": all_modifiers,
#             "product_modifiers": product_modifiers,
#         },
#     )

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
