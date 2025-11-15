from __future__ import annotations

import json

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.response import TemplateResponse
from django.contrib.auth.decorators import permission_required

from mscrInventory.forms import IngredientForm, PackagingForm, RoastProfileForm
from mscrInventory.models import (
    Ingredient,
    IngredientType,
    Packaging,
    RoastProfile,
    SquareUnmappedItem,
    get_or_create_roast_profile,
)
from .inventory import _build_sort_context, _inventory_queryset


def ingredients_dashboard_view(request):
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


def ingredients_table_partial(request):
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
    return _render_ingredient_modal(
        request,
        ingredient=None,
        title="Create Ingredient",
        submit_label="Create",
    )


@permission_required("mscrInventory.change_ingredient", raise_exception=True)
def ingredient_edit_modal(request, pk: int):
    ingredient = get_object_or_404(Ingredient, pk=pk)
    return _render_ingredient_modal(
        request,
        ingredient=ingredient,
        title=f"Edit {ingredient.name}",
        submit_label="Save Changes",
    )
