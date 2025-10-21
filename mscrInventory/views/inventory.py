# mscrInventory/views/inventory.py
from django.db.models import F, Sum
from django.shortcuts import render
from django.views.decorators.http import require_POST
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from decimal import Decimal, InvalidOperation
from mscrInventory.models import Ingredient, StockEntry


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

    context = {
        "total_ingredients": total_ingredients,
        "total_low_stock": total_low_stock,
        "total_cost": total_cost,
        "low_stock_ingredients": low_stock_ingredients,
        "all_ingredients": all_ingredients,
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


@require_POST
def bulk_add_stock(request):
    """Creates multiple StockEntry records and updates ingredient metadata."""
    data = request.POST
    # temp debug
    print("📦 POST KEYS:", list(data.keys()))
    print("📦 POST ITEMS:", data)
    # end temp debug

    items = zip(
        data.getlist("ingredient"),
        data.getlist("quantity_added"),
        data.getlist("cost_per_unit"),
        data.getlist("case_size"),
        data.getlist("lead_time"),
    )

    for ing_id, qty, cost, case, lead in items:
        if not qty or not cost:
            continue
        ing = Ingredient.objects.get(pk=ing_id)
        try:
            qty_val = Decimal(qty)
            cost_val = Decimal(cost)
        except InvalidOperation:
            continue  # skip invalid rows

        if qty_val <= 0 or cost_val < 0:
            continue

        StockEntry.objects.create(
            ingredient=ing,
            quantity_added=qty_val,
            cost_per_unit=cost_val,
            source="bulk",
            note="Bulk add via dashboard",
        )
        # Update metadata
        if case:
            ing.case_size = case
        if lead:
            ing.lead_time = lead
        ing.save(update_fields=["case_size", "lead_time", "last_updated"])

    # ✅ Return success fragment that triggers dashboard refresh + closes modal
    return render(request, "inventory/_bulk_add_success.html")


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
    all_ingredients = Ingredient.objects.select_related("type").order_by("name")
    return render(request, "inventory/_all_ingredients.html", {"all_ingredients": all_ingredients})
