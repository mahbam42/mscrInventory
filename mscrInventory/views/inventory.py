# mscrInventory/views/inventory.py
from django.db.models import F, Sum
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from decimal import Decimal, InvalidOperation
from mscrInventory.models import Ingredient, StockEntry, IngredientType


# -----------------------------
# DASHBOARD
# -----------------------------
def inventory_dashboard_view(request):
    """Display inventory with low stock, totals, and editable table."""
    low_stock_ingredients = Ingredient.objects.filter(
        current_stock__lte=F("reorder_point")
    ).order_by("name")

    all_ingredients = Ingredient.objects.select_related("type", "unit_type").order_by("name")

    total_ingredients = all_ingredients.count()
    total_low_stock = low_stock_ingredients.count()
    total_cost = (
        Ingredient.objects.aggregate(
            total=Sum(F("current_stock") * F("average_cost_per_unit"))
        )["total"]
        or 0
    )
    ingredient_types = IngredientType.objects.order_by("name")
    
    context = {
        "total_ingredients": total_ingredients,
        "total_low_stock": total_low_stock,
        "total_cost": total_cost,
        "low_stock_ingredients": low_stock_ingredients,
        "all_ingredients": all_ingredients,
        "ingredient_types": ingredient_types,
    }
    return render(request, "inventory/dashboard.html", context)

# -----------------------------
# INLINE ACTIONS
# -----------------------------
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


# -----------------------------
# BULK ADD MODAL
# -----------------------------
def bulk_add_modal(request):
    """Render the bulk stock modal."""
    all_ingredients = Ingredient.objects.select_related("type", "unit_type").order_by("type__name", "name")
    return render(request, "inventory/_bulk_add_modal.html", {"all_ingredients": all_ingredients})


# mscrInventory/views/inventory.py
from decimal import Decimal, InvalidOperation
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from mscrInventory.models import Ingredient, StockEntry
import json


@require_POST
def bulk_add_stock(request):
    """Create multiple StockEntry records and refresh dashboard via HTMX triggers."""
    data = request.POST
    items = zip(
        data.getlist("ingredient"),
        data.getlist("Rowquantity_added"),
        data.getlist("Rowcost_per_unit"),
        data.getlist("Rowcase_size"),
        data.getlist("Rowlead_time"),
    )

    created = 0

    with transaction.atomic():
        for ing_id, qty, cost, case, lead in items:
            if not qty or not cost:
                continue

            try:
                ing = Ingredient.objects.get(pk=ing_id)
                qty_val = Decimal(qty)
                cost_val = Decimal(cost)
            except (Ingredient.DoesNotExist, InvalidOperation):
                continue

            # Create new StockEntry
            StockEntry.objects.create(
                ingredient=ing,
                quantity_added=qty_val,
                cost_per_unit=cost_val,
                source="bulk",
                note="Bulk add via dashboard",
            )

            # Update metadata fields
            if case:
                ing.case_size = case
            if lead:
                ing.lead_time = lead
            ing.save(update_fields=["case_size", "lead_time", "last_updated"])

            created += 1

        # ✅ Use HX-Trigger to refresh tables and show a message (no modal re-render)
        response = JsonResponse({"status": "success"})
        response["HX-Trigger"] = json.dumps({
            "inventory:refresh": True,
            "showMessage": {
                "text": (
                    f"✅ {created} stock entries added successfully!"
                    if created else "⚠️ No valid stock entries were added."
                ),
                "level": "success" if created else "warning",
            }
        })
        return response

# --- Populate bulk add modal with ingredient details --->
def ingredient_details(request, pk):
    """Return JSON with current stock data for the selected ingredient."""
    ing = Ingredient.objects.filter(pk=pk).select_related("type", "unit_type").first()
    if not ing:
        return JsonResponse({"error": "Ingredient not found"}, status=404)

    data = {
        "case_size": ing.case_size or 0,
        "lead_time": ing.lead_time or 0,
        "average_cost_per_unit": str(ing.average_cost_per_unit or ""),
        #"unit_type": ing.unit_type.name if ing.unit_type else "",
    }
    return JsonResponse(data)


# -----------------------------
# PARTIALS (for HTMX refresh)
# -----------------------------
def inventory_low_stock_partial(request):
    """Return the low-stock table partial."""
    low_stock_ingredients = Ingredient.objects.filter(
        current_stock__lte=F("reorder_point")
    ).order_by("name")
    return render(request, "inventory/_low_stock.html", {"low_stock_ingredients": low_stock_ingredients})


def inventory_all_ingredients_partial(request):
    """Return the all-ingredients table partial."""
    """Return the full All Ingredients table partial (with optional filters)."""
    qs = Ingredient.objects.select_related("type").order_by("name")
    type_id = request.GET.get("type")
    search = request.GET.get("q")

    if type_id:
        qs = qs.filter(type_id=type_id)
    if search:
        qs = qs.filter(name__icontains=search)

    return render(request, "inventory/_all_ingredients.html", {"all_ingredients": qs})
