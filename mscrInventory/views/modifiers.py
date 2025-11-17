"""Modifier catalog views, bulk importer, and explorer endpoints."""

import csv
import io
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.contrib import messages
from django.db import IntegrityError, transaction

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.response import TemplateResponse
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import permission_required

from urllib.parse import urlencode


from mscrInventory.models import (
    Ingredient,
    IngredientType,
    Product,
    RecipeModifier,
    RecipeModifierAlias,
    UnitType,
)
from mscrInventory.utils.modifier_explorer import ModifierExplorerAnalyzer
from importers._handle_extras import normalize_modifier


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
    """Return the JSON-friendly representation used by the modal."""
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
    """Serialize an queryset of modifiers for modal consumption."""
    return [
        _serialize_modifier(modifier, ingredient_type_lookup)
        for modifier in modifiers
    ]


def _group_modifiers_by_type(modifiers):
    """Group modifiers by ingredient type for accordion rendering."""
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
    """Organize ingredients by type for selection lists."""
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
    """Pre-compute all the context needed for the rules modal."""
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
    """Render the modifier modal template with optional HTMX trigger."""
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


@permission_required("mscrInventory.change_recipemodifier", raise_exception=True)
def modifier_rules_modal(request):
    """Handle GET/POST traffic for the modal that edits modifier rules."""
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


@permission_required("mscrInventory.change_recipemodifier", raise_exception=True)
def create_modifier(request):
    """Persist a new RecipeModifier from modal form submissions."""
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


@permission_required("mscrInventory.change_recipemodifier", raise_exception=True)
def import_modifiers_modal(request):
    """Render the modal where CSV uploads can be initiated."""
    return render(request, "modifiers/_import_modifiers.html")


@permission_required("mscrInventory.change_recipemodifier", raise_exception=True)
@require_POST
def import_modifiers_csv(request):
    """Validate a modifier CSV upload and present preview results."""
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


@permission_required("mscrInventory.change_recipemodifier", raise_exception=True)
@require_POST
def confirm_modifiers_import(request):
    """Create RecipeModifier rows from the validated CSV preview."""
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


@permission_required("mscrInventory.view_recipemodifier", raise_exception=True)
def export_modifiers_csv(request):
    """Stream all modifiers in a format compatible with the importer."""
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


@permission_required("mscrInventory.view_recipemodifier", raise_exception=True)
def download_modifiers_template(request):
    """Provide the canonical CSV template required for imports."""
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

@permission_required("mscrInventory.change_recipemodifier", raise_exception=True)
def edit_modifier_extra_view(request, modifier_id):
    """Display an edit form for modifier extras such as target selectors."""
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


@permission_required("mscrInventory.view_recipemodifier", raise_exception=True)
def modifier_explorer_view(request):
    """Render the interactive modifier explorer with filtering tools."""
    analyzer = ModifierExplorerAnalyzer()
    report = analyzer.analyze()

    include_known_products = (request.GET.get('include_known_products') or '').lower() == 'true'
    classification = (request.GET.get('classification') or 'all').lower()
    search_term_raw = (request.GET.get('q') or '').strip()
    search_term = search_term_raw.lower()
    export_format = (request.GET.get('format') or '').lower()

    product_lookup = {
        normalize_modifier(name): name
        for name in Product.objects.values_list('name', flat=True)
    }
    matched_unknown_product_count = 0
    for insight in report.insights.values():
        match = product_lookup.get(insight.normalized)
        insight.product_match_name = match
        if match and insight.classification == 'unknown':
            matched_unknown_product_count += 1

    insights = sorted(report.insights.values(), key=lambda insight: insight.total_count, reverse=True)
    group_keys = ['known', 'alias', 'fuzzy', 'unknown']

    totals_by_classification = {key: 0 for key in group_keys}
    for insight in insights:
        key = insight.classification if insight.classification in totals_by_classification else 'unknown'
        if (
            key == 'unknown'
            and not include_known_products
            and insight.matches_product
        ):
            continue
        totals_by_classification[key] += 1

    def matches_filters(insight):
        if classification in group_keys and insight.classification != classification:
            return False
        if (
            classification == 'unknown'
            and not include_known_products
            and insight.classification == 'unknown'
            and insight.matches_product
        ):
            return False
        if search_term:
            haystack = [
                insight.normalized,
                insight.modifier_name or '',
                insight.alias_label or '',
            ]
            haystack.extend(insight.raw_labels.keys())
            haystack.extend(insight.items.keys())
            return any(search_term in (token or '').lower() for token in haystack if token)
        return True

    filtered = [insight for insight in insights if matches_filters(insight)]

    if export_format == 'csv':
        fieldnames = [
            'normalized',
            'total_count',
            'classification',
            'modifier_id',
            'modifier_name',
            'modifier_behavior',
            'alias_label',
            'top_raw_labels',
            'top_items',
        ]
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="modifier_explorer.csv"'
        writer = csv.DictWriter(response, fieldnames=fieldnames)
        writer.writeheader()
        for insight in filtered:
            writer.writerow(insight.to_csv_row())
        return response

    grouped = {key: [] for key in group_keys}
    for insight in filtered:
        key = insight.classification if insight.classification in grouped else 'unknown'
        grouped[key].append(insight)

    for bucket in grouped.values():
        bucket.sort(key=lambda insight: insight.total_count, reverse=True)

    co_occurrence_rows = [
        {
            'left': left,
            'right': right,
            'count': count,
        }
        for (left, right), count in sorted(
            report.co_occurrence_pairs.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:25]
    ]

    recipe_modifiers = RecipeModifier.objects.order_by('name').only('id', 'name')

    context = {
        'classification': classification,
        'search_term': search_term_raw,
        'grouped': grouped,
        'total_modifiers': len(filtered),
        'total_available': len(insights),
        'classification_totals': totals_by_classification,
        'filtered_counts': {key: len(value) for key, value in grouped.items()},
        'source_files': report.source_files,
        'co_occurrence_rows': co_occurrence_rows,
        'recipe_modifiers': recipe_modifiers,
        'include_known_products': include_known_products,
        'matched_unknown_product_count': matched_unknown_product_count,
    }

    return render(request, 'modifiers/explorer.html', context)


@permission_required("mscrInventory.change_recipemodifier", raise_exception=True)
@require_POST
def create_modifier_alias(request):
    """Handle alias creation requests from the explorer UI."""
    modifier_id = request.POST.get('modifier_id')
    raw_label = (request.POST.get('raw_label') or '').strip()
    classification = request.POST.get('classification') or ''
    search_term = request.POST.get('q') or ''

    include_known_products_raw = request.POST.get('include_known_products')
    include_known_products = include_known_products_raw == 'true'

    if not modifier_id or not raw_label:
        messages.error(request, 'Select a RecipeModifier and provide an alias label.')
        return redirect(
            _modifier_explorer_redirect(
                classification,
                search_term,
                include_known_products if include_known_products_raw is not None else None,
            )
        )

    modifier = get_object_or_404(RecipeModifier, pk=modifier_id)
    normalized = normalize_modifier(raw_label)

    alias, created = RecipeModifierAlias.objects.update_or_create(
        normalized_label=normalized,
        defaults={'modifier': modifier, 'raw_label': raw_label},
    )

    if created:
        messages.success(request, f'✅ Created alias "{raw_label}" for {modifier.name}.')
    else:
        messages.success(request, f'✅ Updated alias "{raw_label}" to {modifier.name}.')

    return redirect(
        _modifier_explorer_redirect(
            classification,
            search_term,
            include_known_products if include_known_products_raw is not None else None,
        )
    )


def _modifier_explorer_redirect(
    classification: str,
    search_term: str,
    include_known_products: Optional[bool] = None,
):
    """Build a redirect to the explorer view preserving filters."""
    params = {}
    classification = (classification or '').strip().lower()
    if classification and classification != 'all':
        params['classification'] = classification
    if search_term:
        params['q'] = search_term
    if include_known_products:
        params['include_known_products'] = 'true'

    url = reverse('modifier_explorer')
    if params:
        url = f"{url}?{urlencode(params)}"
    return url
