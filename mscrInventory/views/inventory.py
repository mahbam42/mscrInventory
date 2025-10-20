# mscrInventory/views/inventory.py
from django.db.models import F, Sum
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from mscrInventory.models import Ingredient, StockEntry

def inventory_dashboard(request):
    low_stock_ingredients = Ingredient.objects.filter(
        stock_quantity__lte=F("reorder_point")
    ).order_by("name")

    total_ingredients = Ingredient.objects.count()
    total_low_stock = low_stock_ingredients.count()
    total_cost = (
        Ingredient.objects.aggregate(
            total=Sum(F("stock_quantity") * F("cost_per_unit"))
        )["total"]
        or 0
    )

    context = {
        "total_ingredients": total_ingredients,
        "total_low_stock": total_low_stock,
        "total_cost": total_cost,
        "low_stock_ingredients": low_stock_ingredients,
    }
    return render(request, "inventory/dashboard.html", context)


def inventory_dashboard_view(request):
    return render(request, "inventory/dashboard.html")

@require_POST
def update_ingredient(request, pk):
    """Inline update for ingredient fields."""
    ing = Ingredient.objects.get(pk=pk)
    fields = ["current_stock", "case_size", "reorder_point", "average_cost_per_unit"]
    for f in fields:
        if f in request.POST:
            val = request.POST.get(f)
            if val not in ("", None):
                setattr(ing, f, val)
    ing.save(update_fields=fields + ["last_updated"])
    return render(request, "inventory/_ingredient_row.html", {"i": ing})


@require_POST
def add_case(request, pk):
    """Adds one case to stock using case_size and average_cost_per_unit."""
    ing = Ingredient.objects.get(pk=pk)
    if not ing.case_size:
        return JsonResponse({"error": "No case size defined."}, status=400)
    StockEntry.objects.create(
        ingredient=ing,
        quantity_added=ing.case_size,
        cost_per_unit=ing.average_cost_per_unit,
        source="manual",
        note="Added case from dashboard",
    )
    ing.refresh_from_db()
    return render(request, "inventory/_ingredient_row.html", {"i": ing})


@require_POST
def bulk_add_stock(request):
    """Creates multiple StockEntry records from modal submission."""
    data = request.POST
    items = zip(
        data.getlist("ingredient"),
        data.getlist("quantity_added"),
        data.getlist("cost_per_unit"),
    )
    for ing_id, qty, cost in items:
        if not qty or not cost:
            continue
        ing = Ingredient.objects.get(pk=ing_id)
        StockEntry.objects.create(
            ingredient=ing,
            quantity_added=qty,
            cost_per_unit=cost,
            source="bulk",
            note="Bulk add via dashboard",
        )
    return JsonResponse({"status": "success"})
