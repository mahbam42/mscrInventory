from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse, JsonResponse, HttpResponseBadRequest
from decimal import Decimal, InvalidOperation
from django.views.decorators.http import require_http_methods, require_POST
from django.db import transaction
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.contrib import messages
from datetime import datetime
from pathlib import Path
from decimal import Decimal
import csv, io, json
from ..models import Product, Ingredient, RecipeItem, RecipeModifier

LOG_DIR = Path("archive/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "import_recipes.log"

def log_import(action: str, message: str):
    """Append an entry to the recipe import log."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.write_text(
        f"[{timestamp}] {action}: {message}\n",
        encoding="utf-8",
    )

def recipes_dashboard_view(request):
    category = request.GET.get("category", "").strip()
    query = request.GET.get("q", "").strip()

    products = Product.objects.all().order_by("name")

    # Treat 'none' (or similar) as no filter
    if category.lower() in ("none", "null"):
        category = ""

    if category:
        # Accept either ID or name
        if category.isdigit():
            products = products.filter(categories__id=int(category))
        else:
            products = products.filter(categories__name=category)

    if query:
        products = products.filter(name__icontains=query)

    # Build available categories
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
        "categories": categories,
        "selected_category": category,
        "base_items": base_items,
    }

    # 🧩 HTMX support: only return the table partial when requested
    if request.headers.get("HX-Request"):
        return TemplateResponse(request, "recipes/_table.html", ctx)

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
    category = request.GET.get("category", "").strip()
    query = request.GET.get("q", "").strip()

    products = Product.objects.all().order_by("name")

    if category:
        if category.isdigit():
            products = products.filter(categories__id=int(category))
        else:
            products = products.filter(categories__name__icontains=category)

    if query:
        products = products.filter(name__icontains=query)

    ctx = {"products": products}

    # ✅ Always return an HttpResponse
    return render(request, "recipes/_table.html", ctx)

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

def export_recipes_csv(request):
    """Export all recipes and their ingredient breakdowns as CSV."""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="recipes_export.csv"'
    writer = csv.writer(response)

    writer.writerow([
        "product_id",
        "product_name",
        "categories",
        "ingredient_id",
        "ingredient_name",
        "quantity",
        "average_cost_per_unit",
        "cogs_subtotal",
    ])

    # Iterate through all recipes with prefetch for performance
    recipes = Product.objects.prefetch_related("recipe_items__ingredient", "categories").all().order_by("name")

    for product in recipes:
        categories = ", ".join([c.name for c in product.categories.all()])
        for item in product.recipe_items.all():
            ingredient = item.ingredient
            if not ingredient:
                continue
            qty = Decimal(item.quantity or 0)
            cost = Decimal(ingredient.average_cost_per_unit or 0)
            subtotal = qty * cost
            writer.writerow([
                product.id,
                product.name,
                categories,
                ingredient.id,
                ingredient.name,
                qty,
                cost,
                subtotal.quantize(Decimal("0.0001")),
            ])

    return response


def import_recipes_modal(request):
    """Render upload modal."""
    return render(request, "recipes/_import_recipes.html")


@require_POST
def import_recipes_csv(request):
    """Parse CSV, validate rows, show preview (supports dry-run)."""
    csv_file = request.FILES.get("file")
    dry_run = request.POST.get("dry_run") == "on"

    if not csv_file:
        messages.error(request, "⚠️ No file uploaded.")
        return redirect("recipes_dashboard")

    decoded = csv_file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))

    valid_rows, invalid_rows = [], []

    for row in reader:
        product_id = row.get("product_id") or ""
        ingredient_id = row.get("ingredient_id") or ""
        qty = row.get("quantity") or ""

        if not product_id or not ingredient_id:
            invalid_rows.append({**row, "error": "Missing product_id or ingredient_id"})
            continue

        try:
            product = Product.objects.get(pk=product_id)
        except Product.DoesNotExist:
            invalid_rows.append({**row, "error": "Product not found"})
            continue

        try:
            ingredient = Ingredient.objects.get(pk=ingredient_id)
        except Ingredient.DoesNotExist:
            invalid_rows.append({**row, "error": "Ingredient not found"})
            continue

        try:
            qty_val = Decimal(qty or "0")
        except Exception:
            invalid_rows.append({**row, "error": "Invalid quantity"})
            continue

        valid_rows.append({
            "product_id": product.id,
            "product_name": product.name,
            "ingredient_id": ingredient.id,
            "ingredient_name": ingredient.name,
            "quantity": str(qty_val),
        })
        
    if dry_run:
        dry_log = LOG_DIR / f"import_recipes_dryrun_{datetime.now():%Y%m%d}.txt"
        dry_log.write_text(json.dumps(valid_rows, indent=2))
    else:
        log_import(
            "DRY-RUN" if dry_run else "PREVIEW",
            f"{len(valid_rows)} valid, {len(invalid_rows)} invalid uploaded by {request.user if request.user.is_authenticated else 'anonymous'}"
        )

    ctx = {
    "valid_rows": valid_rows,
    "invalid_rows": invalid_rows,
    "count_valid": len(valid_rows),
    "count_invalid": len(invalid_rows),
    "dry_run": dry_run,
    "collapse_valid": len(valid_rows) > 50,
    "valid_rows_json": json.dumps(valid_rows),  # ✅ add this
    }
    return render(request, "recipes/_import_recipes_preview.html", ctx)

@require_POST
def confirm_recipes_import(request):
    """Write validated CSV rows into RecipeItems."""
    data_json = request.POST.get("valid_rows") or request.body.decode("utf-8")

    try:
        # Some browsers double-encode JSON through hx-vals
        rows = json.loads(data_json)
        # If it’s a string again (nested JSON), decode one more level
        if isinstance(rows, str):
            rows = json.loads(rows)
    except Exception as e:
        return JsonResponse(
            {"status": "error", "message": f"Invalid JSON payload: {e}"},
            status=400,
        )

    created, updated = 0, 0

    with transaction.atomic():
        for row in rows:
            try:
                product = Product.objects.get(pk=row["product_id"])
                ingredient = Ingredient.objects.get(pk=row["ingredient_id"])
                qty_val = Decimal(row["quantity"])

                obj, created_flag = RecipeItem.objects.update_or_create(
                    product=product,
                    ingredient=ingredient,
                    defaults={"quantity": qty_val},
                )
                created += int(created_flag)
                updated += int(not created_flag)
            except Exception as e:
                # you can log or skip bad rows silently for now
                continue

    response = JsonResponse({"status": "success"})

    log_import(
        "IMPORT",
        f"{created} created, {updated} updated by {request.user if request.user.is_authenticated else 'anonymous'}"
    )

    response["HX-Trigger"] = json.dumps({
        "recipes:refresh": True,
        "showMessage": {
            "text": f"✅ {created} created, {updated} updated from CSV.",
            "level": "success",
        },
    })
    return response

def download_recipes_template(request):
    """Generate a blank CSV template for recipe imports."""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="recipes_template.csv"'
    writer = csv.writer(response)
    writer.writerow(["product_id", "product_name", "ingredient_id", "ingredient_name", "quantity"])
    writer.writerow(["101", "Demo Latte", "12", "Espresso", "2.0"])
    writer.writerow(["101", "Demo Latte", "14", "Milk", "1.0"])
    writer.writerow(["102", "Hot Brew", "22", "Cold Brew Base", "1.0"])
    return response
