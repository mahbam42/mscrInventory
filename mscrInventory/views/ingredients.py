"""Ingredient CRUD flow views, CSV import/export, and HTMX helpers."""

from __future__ import annotations

import csv
import io
import json
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.response import TemplateResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from mscrInventory.forms import IngredientForm, PackagingForm, RoastProfileForm
from mscrInventory.models import (
    Ingredient,
    IngredientType,
    Packaging,
    RoastProfile,
    SquareUnmappedItem,
    UnitType,
    get_or_create_roast_profile,
)
from .inventory import _build_sort_context, _inventory_queryset


@permission_required("mscrInventory.view_ingredient", raise_exception=True)
def ingredients_dashboard_view(request):
    """Render the ingredient dashboard or its HTMX table as needed."""
    ingredient_types = IngredientType.objects.exclude(name__iexact="extra").order_by("name")
    unresolved_count = SquareUnmappedItem.objects.filter(resolved=False, ignored=False).count()

    context = {
        "ingredient_types": ingredient_types,
        "search_query": request.GET.get("q", "").strip(),
        "active_type": request.GET.get("type", "").strip(),
        "unresolved_count": unresolved_count,
    }

    if request.headers.get("HX-Request"):
        return ingredients_table_partial(request)

    return render(request, "ingredients/dashboard.html", context)


@permission_required("mscrInventory.view_ingredient", raise_exception=True)
def ingredients_table_partial(request):
    """Return the sortable table partial for the ingredient dashboard."""
    search_query = request.GET.get("q", "").strip()
    active_type = request.GET.get("type", "").strip()
    sort_key = request.GET.get("sort", "name")
    direction = request.GET.get("direction", "asc")

    sort_map = {
        "name": "name",
        "category": "type__name",
        "current_stock": "current_stock",
        "case_size": "case_size",
        "reorder_point": "reorder_point",
        "avg_cost": "average_cost_per_unit",
    }

    if sort_key not in sort_map:
        sort_key = "name"
    if direction not in {"asc", "desc"}:
        direction = "asc"

    order_by = sort_map[sort_key]
    if direction == "desc":
        order_by = f"-{order_by}"

    qs = _inventory_queryset().select_related("type", "unit_type")

    if active_type:
        if active_type.isdigit():
            qs = qs.filter(type_id=int(active_type))
        else:
            qs = qs.filter(type__name__iexact=active_type)

    if search_query:
        qs = qs.filter(Q(name__icontains=search_query) | Q(type__name__icontains=search_query))

    qs = qs.order_by(order_by)

    toggle_directions, sort_indicators = _build_sort_context(sort_key, direction, sort_map=sort_map)

    context = {
        "all_ingredients": qs,
        "toggle_directions": toggle_directions,
        "sort_indicators": sort_indicators,
        "search_query": search_query,
        "active_type": active_type,
    }

    return TemplateResponse(request, "ingredients/_table.html", context)


def _render_ingredient_modal(
    request,
    *,
    ingredient: Ingredient | None = None,
    title: str,
    submit_label: str,
):
    """Shared helper that renders the create/edit ingredient modal."""
    ingredient_types = IngredientType.objects.exclude(name__iexact="extra").order_by("name")
    roast_type_ids = [
        str(t.pk) for t in ingredient_types if IngredientForm.requires_roast_fields(t)
    ]
    packaging_type_ids = [
        str(t.pk) for t in ingredient_types if IngredientForm.requires_packaging_fields(t)
    ]

    form = IngredientForm(request.POST or None, instance=ingredient)
    roast_form = RoastProfileForm(request.POST or None, ingredient=ingredient, prefix="roast")
    packaging_form = PackagingForm(request.POST or None, ingredient=ingredient, prefix="packaging")

    if request.method == "POST":
        if form.is_valid():
            selected_type = form.cleaned_data.get("type")
            needs_roast = IngredientForm.requires_roast_fields(selected_type)
            needs_packaging = IngredientForm.requires_packaging_fields(selected_type)

            roast_valid = not needs_roast or roast_form.is_valid()
            packaging_valid = not needs_packaging or packaging_form.is_valid()

            if roast_valid and packaging_valid:
                with transaction.atomic():
                    ingredient_obj = form.save()

                    if needs_roast:
                        profile = get_or_create_roast_profile(ingredient_obj)
                        if profile:
                            profile.bag_size = roast_form.cleaned_data.get("bag_size")
                            profile.grind = roast_form.cleaned_data.get("grind")
                            profile.save(update_fields=["bag_size", "grind"])
                    else:
                        try:
                            ingredient_obj.roastprofile.delete()
                        except RoastProfile.DoesNotExist:  # type: ignore[attr-defined]
                            pass

                    if needs_packaging:
                        try:
                            packaging_obj = ingredient_obj.packaging
                        except Packaging.DoesNotExist:
                            packaging_obj = Packaging(ingredient_ptr=ingredient_obj)
                        packaging_obj.container = packaging_form.cleaned_data.get("container")
                        packaging_obj.temp = packaging_form.cleaned_data.get("temp") or packaging_obj.temp
                        multiplier = packaging_form.cleaned_data.get("multiplier")
                        if multiplier is not None:
                            packaging_obj.multiplier = multiplier
                        packaging_obj.save()
                        size_labels = packaging_form.cleaned_data.get("size_labels")
                        expands_to = packaging_form.cleaned_data.get("expands_to")
                        if size_labels is not None:
                            packaging_obj.size_labels.set(size_labels)
                        if expands_to is not None:
                            packaging_obj.expands_to.set(expands_to)
                    else:
                        Packaging.objects.filter(pk=ingredient_obj.pk).delete()

                verb = "created" if ingredient is None else "updated"
                response = HttpResponse(status=204)
                response["HX-Trigger"] = json.dumps(
                    {
                        "ingredient:refresh": True,
                        "closeModal": True,
                        "showMessage": {
                            "text": f"Ingredient {verb} successfully.",
                            "level": "success",
                        },
                    }
                )
                return response
        # fallthrough to re-render form with errors

    if form.is_bound:
        selected_type_id = str(form.data.get("type", "")).strip()
    else:
        selected_type_id = str(form.instance.type_id or form.initial.get("type") or "")

    return render(
        request,
        "ingredients/_form_modal.html",
        {
            "form": form,
            "roast_form": roast_form,
            "packaging_form": packaging_form,
            "title": title,
            "submit_label": submit_label,
            "roast_type_ids": roast_type_ids,
            "packaging_type_ids": packaging_type_ids,
            "selected_type_id": selected_type_id,
        },
    )


@permission_required("mscrInventory.change_ingredient", raise_exception=True)
def ingredient_create_modal(request):
    """Handle the create modal submission for a new ingredient."""
    return _render_ingredient_modal(
        request,
        ingredient=None,
        title="Create Ingredient",
        submit_label="Create",
    )


@permission_required("mscrInventory.change_ingredient", raise_exception=True)
def ingredient_edit_modal(request, pk: int):
    """Handle modal updates for an existing ingredient."""
    ingredient = get_object_or_404(Ingredient, pk=pk)
    return _render_ingredient_modal(
        request,
        ingredient=ingredient,
        title=f"Edit {ingredient.name}",
        submit_label="Save Changes",
    )


# -----------------------------
# CSV Import/Export for Ingredients
# -----------------------------
INGREDIENT_IMPORT_HEADERS = [
    "id",
    "name",
    "type_id",
    "type_name",
    "unit_type_id",
    "unit_type_name",
    "case_size",
    "reorder_point",
    "average_cost_per_unit",
    "lead_time",
    "notes",
]


def _parse_decimal(value: str | None, field: str, errors: list[str]) -> Decimal | None:
    """Convert a CSV decimal string to Decimal or collect an error."""
    if value in (None, "", " "):
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        errors.append(f"{field} must be a number.")
        return None


def _parse_int(value: str | None, field: str, errors: list[str]) -> int | None:
    """Convert a CSV integer string to int or collect an error."""
    if value in (None, "", " "):
        return None
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        errors.append(f"{field} must be an integer.")
        return None


@permission_required("mscrInventory.view_ingredient", raise_exception=True)
def export_ingredients_csv(request):
    """Export ingredient details in a round-trippable CSV."""

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="ingredients_export_{timezone.now():%Y%m%d_%H%M}.csv"'
    )
    writer = csv.writer(response)
    writer.writerow(INGREDIENT_IMPORT_HEADERS)

    queryset = Ingredient.objects.select_related("type", "unit_type").order_by("name")
    for ing in queryset:
        writer.writerow(
            [
                ing.id,
                ing.name,
                getattr(ing.type, "id", ""),
                getattr(ing.type, "name", ""),
                getattr(ing.unit_type, "id", ""),
                getattr(ing.unit_type, "name", ""),
                ing.case_size or "",
                ing.reorder_point or "",
                ing.average_cost_per_unit or "",
                ing.lead_time or "",
                (ing.notes or "").replace("\n", " ").strip(),
            ]
        )

    return response


@permission_required("mscrInventory.view_ingredient", raise_exception=True)
def download_ingredients_template(request):
    """Download a clean CSV template matching the ingredient importer headers."""

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="ingredients_template.csv"'
    writer = csv.writer(response)
    writer.writerow(INGREDIENT_IMPORT_HEADERS)
    writer.writerow(["", "New Ingredient", "", "Beans", "", "Ounce", "12", "2.5", "1.2500", "7", "Optional notes"])
    writer.writerow(["101", "Existing Milk", "3", "Dairy", "1", "Fluid Ounce", "24", "1.0", "0.7500", "3", "Leave id to update"])
    return response


@permission_required("mscrInventory.change_ingredient", raise_exception=True)
def import_ingredients_modal(request):
    """Render the upload modal for ingredient CSV imports."""

    return render(
        request,
        "ingredients/_import_ingredients.html",
        {"required_headers": INGREDIENT_IMPORT_HEADERS},
    )


@permission_required("mscrInventory.change_ingredient", raise_exception=True)
@require_POST
def import_ingredients_csv(request):
    """Validate uploaded ingredient CSV rows and render a preview."""

    csv_file = request.FILES.get("file")
    if not csv_file:
        messages.error(request, "⚠️ No file uploaded.")
        return import_ingredients_modal(request)

    decoded = csv_file.read().decode("utf-8")
    reader = csv.DictReader(io.StringIO(decoded))

    valid_rows: list[dict[str, str | int | None]] = []
    invalid_rows: list[dict[str, str]] = []

    for line_no, row in enumerate(reader, start=2):
        errors: list[str] = []

        ing_id_raw = (row.get("id") or "").strip()
        name = (row.get("name") or "").strip()
        type_id = _parse_int(row.get("type_id"), "type_id", errors)
        unit_type_id = _parse_int(row.get("unit_type_id"), "unit_type_id", errors)
        case_size = _parse_int(row.get("case_size"), "case_size", errors)
        reorder_point = _parse_decimal(row.get("reorder_point"), "reorder_point", errors)
        average_cost = _parse_decimal(
            row.get("average_cost_per_unit"), "average_cost_per_unit", errors
        )
        lead_time = _parse_int(row.get("lead_time"), "lead_time", errors)
        notes = (row.get("notes") or "").strip()

        if not name:
            errors.append("Name is required.")

        ingredient = None
        if ing_id_raw:
            try:
                ingredient = Ingredient.objects.get(pk=int(ing_id_raw))
            except (Ingredient.DoesNotExist, ValueError):
                errors.append("Ingredient id not found.")

        if ingredient is None and name:
            ingredient = Ingredient.objects.filter(name__iexact=name).first()

        type_obj = None
        if type_id is not None:
            type_obj = IngredientType.objects.filter(pk=type_id).first()
            if type_obj is None:
                errors.append("type_id not found.")
        elif row.get("type_name"):
            type_obj = IngredientType.objects.filter(name__iexact=row["type_name"].strip()).first()
            if type_obj is None:
                errors.append("type_name not recognized.")

        unit_type_obj = None
        if unit_type_id is not None:
            unit_type_obj = UnitType.objects.filter(pk=unit_type_id).first()
            if unit_type_obj is None:
                errors.append("unit_type_id not found.")
        elif row.get("unit_type_name"):
            unit_type_obj = UnitType.objects.filter(name__iexact=row["unit_type_name"].strip()).first()
            if unit_type_obj is None:
                errors.append("unit_type_name not recognized.")

        if errors:
            invalid_rows.append({**row, "line": line_no, "error": "; ".join(errors)})
            continue

        operation = "update" if ingredient else "create"

        valid_rows.append(
            {
                "id": ingredient.id if ingredient else None,
                "name": name,
                "type_id": type_obj.id if type_obj else None,
                "type_name": type_obj.name if type_obj else (row.get("type_name") or ""),
                "unit_type_id": unit_type_obj.id if unit_type_obj else None,
                "unit_type_name": unit_type_obj.name if unit_type_obj else (row.get("unit_type_name") or ""),
                "case_size": case_size if case_size is not None else "",
                "reorder_point": str(reorder_point) if reorder_point is not None else "",
                "average_cost_per_unit": str(average_cost) if average_cost is not None else "",
                "lead_time": lead_time if lead_time is not None else "",
                "notes": notes,
                "operation": operation,
            }
        )

    context = {
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "count_valid": len(valid_rows),
        "count_invalid": len(invalid_rows),
        "collapse_valid": len(valid_rows) > 50,
        "valid_rows_json": json.dumps(valid_rows),
        "required_headers": INGREDIENT_IMPORT_HEADERS,
    }

    return render(request, "ingredients/_import_ingredients_preview.html", context)


@permission_required("mscrInventory.change_ingredient", raise_exception=True)
@require_POST
def confirm_ingredients_import(request):
    """Persist validated ingredient rows from the preview."""

    payload = request.POST.get("valid_rows") or request.body.decode("utf-8")
    try:
        rows = json.loads(payload)
        if isinstance(rows, str):
            rows = json.loads(rows)
    except Exception as exc:  # pragma: no cover - defensive
        return JsonResponse({"status": "error", "message": str(exc)}, status=400)

    created, updated = 0, 0

    with transaction.atomic():
        for row in rows:
            ingredient = None
            if row.get("id"):
                ingredient = Ingredient.objects.filter(pk=row["id"]).first()

            if ingredient is None:
                ingredient, created_flag = Ingredient.objects.get_or_create(name=row["name"].strip())
                created += int(created_flag)
            else:
                updated += 1

            type_obj = None
            if row.get("type_id"):
                type_obj = IngredientType.objects.filter(pk=row["type_id"]).first()
            elif row.get("type_name"):
                type_obj = IngredientType.objects.filter(name__iexact=row["type_name"].strip()).first()

            unit_type_obj = None
            if row.get("unit_type_id"):
                unit_type_obj = UnitType.objects.filter(pk=row["unit_type_id"]).first()
            elif row.get("unit_type_name"):
                unit_type_obj = UnitType.objects.filter(name__iexact=row["unit_type_name"].strip()).first()

            ingredient.type = type_obj
            ingredient.unit_type = unit_type_obj

            if row.get("case_size") not in ("", None):
                ingredient.case_size = int(row["case_size"])
            if row.get("reorder_point") not in ("", None):
                ingredient.reorder_point = Decimal(str(row["reorder_point"]))
            if row.get("average_cost_per_unit") not in ("", None):
                ingredient.average_cost_per_unit = Decimal(str(row["average_cost_per_unit"]))
            if row.get("lead_time") not in ("", None):
                ingredient.lead_time = int(row["lead_time"])
            ingredient.notes = row.get("notes") or ""
            ingredient.save()

    response = JsonResponse({"status": "success"})
    response["HX-Trigger"] = json.dumps(
        {
            "ingredient:refresh": True,
            "showMessage": {
                "text": f"✅ {created} created, {updated} updated from CSV.",
                "level": "success",
            },
        }
    )
    return response
