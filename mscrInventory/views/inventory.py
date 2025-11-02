# mscrInventory/views/inventory.py
from django.db.models import F, Sum
from django.db import transaction
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST
from django.http import HttpResponse, JsonResponse, QueryDict
from django.contrib import messages
from django.template.loader import render_to_string
from decimal import Decimal, InvalidOperation
from datetime import timezone
import json, csv, io
from itertools import zip_longest
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

@require_POST
def bulk_add_stock(request):
    """Create multiple StockEntry records and refresh dashboard via HTMX triggers."""
    data = request.POST

    #degug data
    print("POST keys:", list(data.keys()))
    print("reason:", data.get("reason"))
    print("note:", data.get("note"))
    print("Rowquantity_added:", data.getlist("Rowquantity_added"))
    # end debug

    reason = data.get("reason") or "Bulk Add"
    note = data.get("note") or "Added via bulk add modal"
    # Use Row* lists if present; otherwise fall back to Modal*
    qty_list = data.getlist("Rowquantity_added") or data.getlist("Modalquantity_added")
    cost_list = data.getlist("Rowcost_per_unit") or data.getlist("Modalcost_per_unit")
    case_list = data.getlist("Rowcase_size") or data.getlist("Modalcase_size")
    lead_list = data.getlist("Rowlead_time") or data.getlist("Modallead_time")
    reorder_list = data.getlist("Rowreorder_point") or []

    # Clean empty strings
    ingredients = [i for i in data.getlist("ingredient") if i.strip()]

    items = zip_longest(ingredients, qty_list, cost_list, case_list, lead_list, reorder_list, fillvalue=None)

    created = 0

    with transaction.atomic():
        for ing_id, qty, cost, case, lead, reorder in items:
            if not ing_id or qty in (None, "", " "):
                continue

            try:
                ing = Ingredient.objects.get(pk=ing_id)
                qty_val = Decimal(str(qty).strip())
                cost_val = Decimal(str(cost or "0").strip())
            except (Ingredient.DoesNotExist, InvalidOperation):
                continue

            # ✅ Create the StockEntry (allow negatives)
            StockEntry.objects.create(
                ingredient=ing,
                quantity_added=qty_val,
                cost_per_unit=cost_val,
                source=reason.lower(),
                note=note,
            )

            # ✅ Update Ingredient stock and metadata
            ing.current_stock = (ing.current_stock or Decimal(0)) + qty_val

            if case:
                ing.case_size = case
            if lead:
                ing.lead_time = lead
            if reorder:
                ing.reorder_point = reorder

            ing.save(
                update_fields=[
                    "current_stock",
                    "case_size",
                    "lead_time",
                    "reorder_point",
                    "last_updated",
                ]
            )

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

# -----------------------------
# CSV Import/Export
# -----------------------------
# --- CSV Export ---
def export_inventory_csv(request):
    """
    Download a point-in-time snapshot of all Ingredients.
    File: inventory_snapshot.csv
    Columns are intentionally simple and stable for round-tripping.
    """
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename=inventory_snapshot_{timezone.now():%Y%m%d_%H%M}.csv'
    writer = csv.writer(response)
    writer.writerow([
        "id",
        "name",
        "type",
        "current_stock",
        "case_size",
        "reorder_point",
        "average_cost_per_unit",
        "lead_time",
    ])

    qs = Ingredient.objects.select_related("type").order_by("name")
    for i in qs:
        writer.writerow([
            i.id,
            i.name,
            getattr(i.type, "name", ""),
            i.current_stock,
            i.case_size,
            i.reorder_point,
            i.average_cost_per_unit,
            i.lead_time,
        ])
    return response

REQUIRED_HEADERS = [
    "id", "name", "type", "quantity_added", "current_stock", "case_size",
    "reorder_point", "average_cost_per_unit", "lead_time"
]

from decimal import Decimal, InvalidOperation
from django.shortcuts import render
from django.views.decorators.http import require_POST
from mscrInventory.models import Ingredient

@require_POST
def import_inventory_csv(request):
    csv_file = request.FILES.get("file")
    if not csv_file:
        return render(request, "inventory/_import_inventory.html", {"error": "⚠️ No file selected."})

    import io, csv
    decoded = csv_file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))

    valid_rows, invalid_rows = [], []

    for line_no, row in enumerate(reader, start=2):
        row_errors = []
        try:
            ing = Ingredient.objects.get(pk=int(row.get("id")))
        except (Ingredient.DoesNotExist, ValueError, TypeError):
            row_errors.append("Invalid Ingredient ID.")
            invalid_rows.append({**row, "line": line_no, "error": "; ".join(row_errors)})
            continue

        # Parse quantity_added and current_stock
        qty_added = row.get("quantity_added")
        current_stock_csv = row.get("current_stock")

        try:
            qty_added = Decimal(qty_added) if qty_added not in (None, "", " ") else None
        except InvalidOperation:
            qty_added = None
            row_errors.append("quantity_added not numeric.")

        try:
            current_stock_csv = Decimal(current_stock_csv) if current_stock_csv not in (None, "", " ") else None
        except InvalidOperation:
            current_stock_csv = None
            row_errors.append("current_stock not numeric.")

        # Derive delta if no explicit quantity_added
        if qty_added is None and current_stock_csv is not None:
            delta = current_stock_csv - (ing.current_stock or Decimal(0))
            if delta > 0:
                qty_added = delta
            else:
                row_errors.append("No stock increase detected.")

        if qty_added is None or "":
            row_errors.append("Quantity must be positive or computable delta.")

        if row_errors:
            invalid_rows.append({**row, "line": line_no, "error": "; ".join(row_errors)})
            continue

        # Build valid entry
        valid_rows.append({
            "ingredient": ing.id,
            "name": ing.name,
            "quantity_added": float(qty_added),
            "cost_per_unit": float(row.get("average_cost_per_unit") or 0),
            "case_size": row.get("case_size") or "",
            "lead_time": row.get("lead_time") or "",
            "reorder_point": row.get("reorder_point") or "",
        })

    return render(request, "inventory/_import_inventory.html", {
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "valid_count": len(valid_rows),
        "invalid_count": len(invalid_rows),
    })

def import_inventory_modal(request):
    """Render the initial upload form for the inventory importer modal."""
    return render(request, "inventory/_import_inventory.html", {"stage": "upload"})

def download_inventory_csv_template(request):
    """Generate and download a blank CSV template with required headers."""

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="inventory_import_template.csv"'
    writer = csv.writer(response)
    writer.writerow(REQUIRED_HEADERS)
    return response

def confirm_inventory_import(request):
    """Apply validated import rows via bulk_add_stock()."""
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"status": "error", "message": "Invalid JSON payload."}, status=400)

    # Build a QueryDict to mimic a POST
    qd = QueryDict(mutable=True)
    for r in payload:
        qd.update({
            "ingredient": str(r["ingredient"]),
            "Rowquantity_added": str(r["quantity_added"]),
            "Rowcost_per_unit": str(r.get("cost_per_unit") or 0),
            "Rowcase_size": str(r.get("case_size") or ""),
            "Rowlead_time": str(r.get("lead_time") or ""),
        })
        qd.appendlist('Rowreorder_point', str(r.get("reorder_point") or "")) #refactor to qd.update

    request.POST = qd
    return bulk_add_stock(request)