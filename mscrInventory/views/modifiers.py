import csv
import io
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.response import TemplateResponse
from django.views.decorators.http import require_POST

from mscrInventory.models import Ingredient, IngredientType, RecipeModifier, UnitType


REQUIRED_MODIFIER_COLUMNS = [
    "name",
    "type",
    "ingredient",
    "base quantity",
    "unit",
    "cost per unit",
    "price per unit",
]


def _serialize_modifier(modifier, ingredient_type_lookup):
    target_selector = modifier.target_selector or {}
    replaces = modifier.replaces or {}
    raw_by_type = target_selector.get("by_type", []) or []

    normalized_by_type: list[str] = []
    for value in raw_by_type:
        if isinstance(value, int):
            normalized_by_type.append(str(value))
            continue
        if isinstance(value, str):
            if value.isdigit():
                normalized_by_type.append(value)
                continue
            match = ingredient_type_lookup.get(value.strip().lower())
            if match:
                normalized_by_type.append(str(match))
                continue
        # preserve unknown values for debugging; UI will ignore them
        normalized_by_type.append(str(value))

    return {
        "id": modifier.id,
        "name": modifier.name,
        "behavior": modifier.behavior,
        "quantity_factor": str(modifier.quantity_factor or "1"),
        "target_selector": {
            "by_type": normalized_by_type,
            "by_name": target_selector.get("by_name", []),
        },
        "replaces": {
            "to": replaces.get("to", []),
        },
        "expands_to": list(modifier.expands_to.values_list("id", flat=True)),
        "ingredient_type_id": modifier.ingredient_type_id,
    }


def _modifier_payload(modifiers, ingredient_type_lookup):
    return [
        _serialize_modifier(modifier, ingredient_type_lookup)
        for modifier in modifiers
    ]


def _group_modifiers_by_type(modifiers):
    grouped = defaultdict(list)
    for modifier in modifiers:
        type_obj = modifier.ingredient_type
        key = modifier.ingredient_type_id
        label = type_obj.name if type_obj else "Uncategorized"
        grouped[(key, label)].append(modifier)

    groups = []

    for (type_id, label), mods in sorted(
        grouped.items(),
        key=lambda item: (item[0][1] or "").lower(),
    ):
        groups.append(
            {
                "code": type_id,
                "label": label or "Uncategorized",
                "modifiers": sorted(mods, key=lambda m: m.name.lower()),
            }
        )

    return groups


def _group_ingredients_by_type(ingredients):
    grouped = defaultdict(list)
    for ingredient in ingredients:
        type_obj = ingredient.type
        key = type_obj.id if type_obj else None
        label = type_obj.name if type_obj else "Uncategorized"
        grouped[(key, label)].append(ingredient)

    ordered = []
    for (key, label), items in sorted(
        grouped.items(),
        key=lambda item: (item[0][1] or "").lower(),
    ):
        ordered.append(
            {
                "code": key,
                "label": label or "Uncategorized",
                "ingredients": sorted(items, key=lambda ing: ing.name.lower()),
            }
        )

    return ordered


def _load_modifier_modal_data():
    modifiers = (
        RecipeModifier.objects
        .select_related("ingredient_type")
        .prefetch_related("expands_to")
        .order_by("ingredient_type__name", "name")
    )
    ingredients = (
        Ingredient.objects.select_related("type")
        .all()
        .order_by("type__name", "name")
    )
    ingredient_types = IngredientType.objects.all().order_by("name")
    unit_types = UnitType.objects.all().order_by("name")

    modifier_groups = _group_modifiers_by_type(modifiers)
    ingredient_groups = _group_ingredients_by_type(ingredients)
    ingredient_type_lookup = {
        (it.name or "").strip().lower(): it.id
        for it in ingredient_types
    }
    serialized = _modifier_payload(modifiers, ingredient_type_lookup)

    return {
        "modifiers": modifiers,
        "ingredients": ingredients,
        "ingredient_groups": ingredient_groups,
        "ingredient_types": ingredient_types,
        "modifier_data": serialized,
        "modifier_json": json.dumps(serialized),
        "behavior_choices": RecipeModifier.ModifierBehavior.choices,
        "modifier_groups": modifier_groups,
        "unit_types": unit_types,
    }


def _render_modifier_modal(request, context_overrides=None, trigger=None):
    context = _load_modifier_modal_data()
    if context_overrides:
        context.update(context_overrides)
    context.setdefault("new_modifier_data", {})
    context.setdefault("new_modifier_errors", {})
    context.setdefault("new_modifier_open", False)
    meta = {
        "selected_id": context.get("selected_modifier_id"),
    }
    context["modifier_meta"] = json.dumps(meta)
    response = TemplateResponse(request, "modifiers/rules_modal.html", context)
    if trigger:
        response["HX-Trigger"] = json.dumps(trigger)
    return response


def modifier_rules_modal(request):
    if request.method == "POST":
        modifier_id = request.POST.get("modifier_id")
        modifier = get_object_or_404(RecipeModifier, pk=modifier_id)

        behavior = request.POST.get("behavior") or modifier.behavior
        quantity_factor_raw = request.POST.get("quantity_factor")
        by_type_raw = [value for value in request.POST.getlist("target_by_type") if value]
        by_type: list[int] = []
        for raw in by_type_raw:
            try:
                by_type.append(int(raw))
            except (TypeError, ValueError):
                lookup = IngredientType.objects.filter(name__iexact=raw).values_list("id", flat=True).first()
                if lookup:
                    by_type.append(int(lookup))
        by_name = [value for value in request.POST.getlist("target_by_name") if value]
        replacement_names = request.POST.getlist("replacement_name")
        replacement_qtys = request.POST.getlist("replacement_qty")
        expands_to_ids = [int(pk) for pk in request.POST.getlist("expands_to") if pk]

        modifier.behavior = behavior

        if quantity_factor_raw:
            try:
                modifier.quantity_factor = Decimal(quantity_factor_raw)
            except (InvalidOperation, TypeError):
                pass

        modifier.target_selector = (
            {"by_type": by_type, "by_name": by_name}
            if (by_type or by_name)
            else None
        )

        replacements = []
        for name, qty in zip(replacement_names, replacement_qtys):
            if not name:
                continue
            try:
                qty_value = Decimal(qty)
            except (InvalidOperation, TypeError):
                qty_value = Decimal("1")
            replacements.append([name, float(qty_value)])

        modifier.replaces = {"to": replacements} if replacements else None

        modifier.save()
        modifier.expands_to.set(expands_to_ids)

        trigger = {
            "showMessage": {"text": f"Updated rules for {modifier.name}.", "level": "success"}
        }
        return _render_modifier_modal(
            request,
            context_overrides={"selected_modifier_id": modifier.id},
            trigger=trigger,
        )

    return _render_modifier_modal(request)


def create_modifier(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    name = (request.POST.get("create_name") or "").strip()
    modifier_type_id = request.POST.get("create_ingredient_type")
    ingredient_id = request.POST.get("create_ingredient")
    base_quantity_raw = request.POST.get("create_base_quantity")
    unit_type_id = request.POST.get("create_unit")
    cost_raw = request.POST.get("create_cost_per_unit")
    price_raw = request.POST.get("create_price_per_unit")

    errors = {}

    if not name:
        errors["name"] = "Name is required."

    if not modifier_type_id:
        errors["ingredient_type"] = "Type is required."

    ingredient_type = None
    if modifier_type_id:
        try:
            ingredient_type = IngredientType.objects.get(pk=modifier_type_id)
        except (ValueError, IngredientType.DoesNotExist):
            errors["ingredient_type"] = "Selected type could not be found."

    ingredient = None
    if not ingredient_id:
        errors["ingredient"] = "Ingredient is required."
    else:
        try:
            ingredient = Ingredient.objects.get(pk=ingredient_id)
        except Ingredient.DoesNotExist:
            errors["ingredient"] = "Selected ingredient could not be found."

    base_quantity = None
    if not base_quantity_raw:
        errors["base_quantity"] = "Base quantity is required."
    else:
        try:
            base_quantity = Decimal(base_quantity_raw)
        except (InvalidOperation, TypeError):
            errors["base_quantity"] = "Enter a valid quantity."

    unit_type = None
    if not unit_type_id:
        errors["unit"] = "Unit is required."
    else:
        try:
            unit_type = UnitType.objects.get(pk=unit_type_id)
        except UnitType.DoesNotExist:
            errors["unit"] = "Selected unit is not available."

    cost_per_unit = Decimal("0.00")
    if cost_raw:
        try:
            cost_per_unit = Decimal(cost_raw)
        except (InvalidOperation, TypeError):
            errors["cost_per_unit"] = "Enter a valid cost."

    price_per_unit = Decimal("0.00")
    if price_raw:
        try:
            price_per_unit = Decimal(price_raw)
        except (InvalidOperation, TypeError):
            errors["price_per_unit"] = "Enter a valid price."

    initial_data = {
        "name": name,
        "ingredient_type": modifier_type_id,
        "ingredient": ingredient_id,
        "base_quantity": base_quantity_raw,
        "unit": unit_type_id,
        "cost_per_unit": cost_raw,
        "price_per_unit": price_raw,
    }

    if errors:
        return _render_modifier_modal(
            request,
            context_overrides={
                "new_modifier_errors": errors,
                "new_modifier_data": initial_data,
                "new_modifier_open": True,
            },
        )

    try:
        modifier = RecipeModifier.objects.create(
            name=name,
            ingredient_type=ingredient_type,
            ingredient=ingredient,
            base_quantity=base_quantity,
            unit=unit_type.abbreviation or unit_type.name,
            behavior=RecipeModifier.ModifierBehavior.ADD,
            quantity_factor=Decimal("1.0"),
            cost_per_unit=cost_per_unit,
            price_per_unit=price_per_unit,
        )
    except IntegrityError:
        errors["name"] = "A modifier with this name already exists."
        return _render_modifier_modal(
            request,
            context_overrides={
                "new_modifier_errors": errors,
                "new_modifier_data": initial_data,
                "new_modifier_open": True,
            },
        )

    trigger = {
        "showMessage": {"text": f"Created modifier {modifier.name}.", "level": "success"}
    }
    return _render_modifier_modal(
        request,
        context_overrides={"selected_modifier_id": modifier.id},
        trigger=trigger,
    )


def import_modifiers_modal(request):
    return render(request, "modifiers/_import_modifiers.html")


@require_POST
def import_modifiers_csv(request):
    csv_file = request.FILES.get("file")
    if not csv_file:
        return render(
            request,
            "modifiers/_import_modifiers.html",
            {"error": "Please upload a CSV file."},
            status=400,
        )

    decoded = csv_file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(decoded))

    if not reader.fieldnames:
        return render(
            request,
            "modifiers/_import_modifiers.html",
            {"error": "The uploaded CSV is missing a header row."},
            status=400,
        )

    headers = [header.strip().lower() for header in reader.fieldnames if header]
    missing = [column for column in REQUIRED_MODIFIER_COLUMNS if column not in headers]
    if missing:
        return render(
            request,
            "modifiers/_import_modifiers.html",
            {
                "error": "Missing required columns: " + ", ".join(missing),
            },
            status=400,
        )

    valid_rows: list[dict] = []
    invalid_rows: list[dict] = []

    for index, row in enumerate(reader, start=2):
        normalized = {
            (key or "").strip().lower(): (value or "").strip()
            for key, value in row.items()
        }

        if not any(normalized.values()):
            continue

        name = normalized.get("name", "")
        if not name:
            invalid_rows.append(
                {
                    "row": index,
                    "name": name,
                    "type": normalized.get("type", ""),
                    "ingredient": normalized.get("ingredient", ""),
                    "error": "Name is required.",
                }
            )
            continue

        if name.startswith("#"):
            continue

        type_name = normalized.get("type", "")
        ingredient_name = normalized.get("ingredient", "")
        unit = normalized.get("unit", "")
        base_quantity_raw = normalized.get("base quantity", "")
        cost_raw = normalized.get("cost per unit", "")
        price_raw = normalized.get("price per unit", "")

        ingredient_type = IngredientType.objects.filter(name__iexact=type_name).first()
        if not ingredient_type:
            invalid_rows.append(
                {
                    "row": index,
                    "name": name,
                    "type": type_name,
                    "ingredient": ingredient_name,
                    "error": "Type not found.",
                }
            )
            continue

        ingredient = Ingredient.objects.filter(name__iexact=ingredient_name).first()
        if not ingredient:
            invalid_rows.append(
                {
                    "row": index,
                    "name": name,
                    "type": type_name,
                    "ingredient": ingredient_name,
                    "error": "Ingredient not found.",
                }
            )
            continue

        if not unit:
            invalid_rows.append(
                {
                    "row": index,
                    "name": name,
                    "type": type_name,
                    "ingredient": ingredient_name,
                    "error": "Unit is required.",
                }
            )
            continue

        try:
            base_quantity = Decimal(base_quantity_raw)
        except (InvalidOperation, TypeError):
            invalid_rows.append(
                {
                    "row": index,
                    "name": name,
                    "type": type_name,
                    "ingredient": ingredient_name,
                    "error": "Invalid base quantity.",
                }
            )
            continue

        try:
            cost_per_unit = Decimal(cost_raw or "0")
        except (InvalidOperation, TypeError):
            invalid_rows.append(
                {
                    "row": index,
                    "name": name,
                    "type": type_name,
                    "ingredient": ingredient_name,
                    "error": "Invalid cost per unit.",
                }
            )
            continue

        try:
            price_per_unit = Decimal(price_raw or "0")
        except (InvalidOperation, TypeError):
            invalid_rows.append(
                {
                    "row": index,
                    "name": name,
                    "type": type_name,
                    "ingredient": ingredient_name,
                    "error": "Invalid price per unit.",
                }
            )
            continue

        valid_rows.append(
            {
                "row": index,
                "name": name,
                "ingredient_type_id": ingredient_type.id,
                "ingredient_type_name": ingredient_type.name,
                "ingredient_id": ingredient.id,
                "ingredient_name": ingredient.name,
                "base_quantity": str(base_quantity),
                "unit": unit,
                "cost_per_unit": str(cost_per_unit),
                "price_per_unit": str(price_per_unit),
            }
        )

    context = {
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "count_valid": len(valid_rows),
        "count_invalid": len(invalid_rows),
        "valid_rows_json": json.dumps(valid_rows),
    }

    return render(request, "modifiers/_import_modifiers_preview.html", context)


@require_POST
def confirm_modifiers_import(request):
    data_json = request.POST.get("valid_rows") or request.body.decode("utf-8")

    try:
        rows = json.loads(data_json)
        if isinstance(rows, str):
            rows = json.loads(rows)
    except json.JSONDecodeError as exc:
        return JsonResponse({"status": "error", "message": str(exc)}, status=400)

    created, updated = 0, 0

    with transaction.atomic():
        for row in rows:
            defaults = {
                "ingredient_type_id": row["ingredient_type_id"],
                "ingredient_id": row["ingredient_id"],
                "base_quantity": Decimal(row["base_quantity"]),
                "unit": row["unit"],
                "cost_per_unit": Decimal(row["cost_per_unit"]),
                "price_per_unit": Decimal(row["price_per_unit"]),
            }

            modifier, created_flag = RecipeModifier.objects.update_or_create(
                name=row["name"],
                defaults=defaults,
            )

            created += int(created_flag)
            updated += int(not created_flag)

    message = f"Imported {created} modifier(s); updated {updated}."
    response = HttpResponse(status=204)
    response["HX-Trigger"] = json.dumps(
        {
            "recipes:refresh": True,
            "showMessage": {"text": f"✅ {message}", "level": "success"},
            "closeModal": True,
        }
    )
    return response


def export_modifiers_csv(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="modifiers_export.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "Name",
            "Type",
            "Ingredient",
            "Base Quantity",
            "Unit",
            "Cost per Unit",
            "Price per Unit",
        ]
    )

    for modifier in RecipeModifier.objects.select_related("ingredient", "ingredient_type").order_by("name"):
        writer.writerow(
            [
                modifier.name,
                modifier.ingredient_type.name if modifier.ingredient_type else "",
                modifier.ingredient.name if modifier.ingredient else "",
                modifier.base_quantity,
                modifier.unit,
                modifier.cost_per_unit,
                modifier.price_per_unit,
            ]
        )

    return response


def download_modifiers_template(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="modifiers_template.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "Name",
            "Type",
            "Ingredient",
            "Base Quantity",
            "Unit",
            "Cost per Unit",
            "Price per Unit",
        ]
    )
    writer.writerow(
        [
            "# Sample Modifier (remove)",
            "Milk",
            "Whole Milk",
            "1.00",
            "oz",
            "0.25",
            "0.75",
        ]
    )
    return response

def edit_modifier_extra_view(request, modifier_id):
    modifier = get_object_or_404(RecipeModifier, pk=modifier_id)
    # stub logic for now
    if request.method == "POST":
        multiplier = request.POST.get("multiplier")
        linked_ingredient_id = request.POST.get("linked_ingredient") or None

        if multiplier:
            modifier.price_per_unit = multiplier  # or separate field if needed
        if linked_ingredient_id:
            modifier.ingredient_id = linked_ingredient_id
        else:
            modifier.ingredient = None

        modifier.save()
        return JsonResponse({"status": "ok", "modifier": modifier.name})

    ingredients = Ingredient.objects.all().order_by("name")
    return render(request, "modifiers/edit_extra_modal.html", {"modifier": modifier, "ingredients": ingredients})
