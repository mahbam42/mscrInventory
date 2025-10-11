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
                # --- 1️⃣ Update ingredient quantities ---
                for key, value in request.POST.items():
                    if key.startswith("quantity_") and value.strip() != "":
                        item_id = key.split("_", 1)[1]
                        try:
                            item = RecipeItem.objects.get(pk=item_id, product=product)
                            new_qty = Decimal(value)
                            if new_qty != item.quantity:
                                item.quantity = new_qty
                                item.save(update_fields=["quantity"])
                        except RecipeItem.DoesNotExist:
                            pass  # could also log this if needed

                # --- 2️⃣ Update modifier selections ---
                # Clear existing modifiers
                product.recipemodifier_set.clear()

                # Re-add checked modifiers
                selected_mod_ids = [
                    key.split("_", 1)[1]
                    for key in request.POST.keys()
                    if key.startswith("modifier_")
                ]
                if selected_mod_ids:
                    mods = RecipeModifier.objects.filter(id__in=selected_mod_ids)
                    # Assuming many-to-many between Product and RecipeModifier (if not, see note below)
                    product.recipemodifier_set.add(*mods)

            return JsonResponse({"success": True, "message": "Recipe updated successfully."})
        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)}, status=400)

    # --- GET method: render modal ---
    recipe_items = RecipeItem.objects.filter(product=product).select_related("ingredient")
    modifiers = models.ManyToManyField("RecipeModifier", blank=True, related_name="products")
    # modifiers = RecipeModifier.objects.all().order_by("type", "name")
    selected_modifiers = product.recipemodifier_set.values_list("id", flat=True)

    context = {
        "product": product,
        "recipe_items": recipe_items,
        "modifiers": modifiers,
        "selected_modifiers": set(selected_modifiers),
    }
    return render(request, "recipes/_edit_modal.html", context)

def edit_recipe_view(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    base_items = product.recipe_items.select_related("ingredient")
    all_modifiers = RecipeModifier.objects.all().order_by("type", "name")
    product_modifiers = product.modifiers.all()

    return render(
        request,
        "recipes/edit_recipe_modal.html",
        {
            "product": product,
            "base_items": base_items,
            "all_modifiers": all_modifiers,
            "product_modifiers": product_modifiers,
        },
    )

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
