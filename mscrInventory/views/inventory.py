# mscrInventory/views/inventory.py
from django.db.models import F, Sum
from django.shortcuts import render
from mscrInventory.models import Ingredient

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
