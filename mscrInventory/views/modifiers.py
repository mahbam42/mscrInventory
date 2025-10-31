import json
from decimal import Decimal, InvalidOperation

from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from mscrInventory.models import (
    Ingredient,
    IngredientType,
    RecipeModifier,
)


def _serialize_modifier(modifier):
    target_selector = modifier.target_selector or {}
    replaces = modifier.replaces or {}
    return {
        "id": modifier.id,
        "name": modifier.name,
        "behavior": modifier.behavior,
        "quantity_factor": str(modifier.quantity_factor or "1"),
        "target_selector": {
            "by_type": target_selector.get("by_type", []),
            "by_name": target_selector.get("by_name", []),
        },
        "replaces": {
            "to": replaces.get("to", []),
        },
        "expands_to": list(modifier.expands_to.values_list("id", flat=True)),
    }


def _modifier_payload(modifiers):
    return [_serialize_modifier(modifier) for modifier in modifiers]


def modifier_rules_modal(request):
    modifiers = RecipeModifier.objects.prefetch_related("expands_to").order_by("type", "name")
    ingredients = Ingredient.objects.all().order_by("name")
    ingredient_types = IngredientType.objects.all().order_by("name")

    behavior_choices = RecipeModifier.ModifierBehavior.choices

    if request.method == "POST":
        modifier_id = request.POST.get("modifier_id")
        modifier = get_object_or_404(RecipeModifier, pk=modifier_id)

        behavior = request.POST.get("behavior") or modifier.behavior
        quantity_factor_raw = request.POST.get("quantity_factor")
        by_type = [value for value in request.POST.getlist("target_by_type") if value]
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

        modifiers = RecipeModifier.objects.prefetch_related("expands_to").order_by("type", "name")

        trigger = {"showMessage": {"text": f"Updated rules for {modifier.name}.", "level": "success"}}

        serialized = _modifier_payload(modifiers)
        response = render(
            request,
            "modifiers/rules_modal.html",
            {
                "modifiers": modifiers,
                "ingredients": ingredients,
                "ingredient_types": ingredient_types,
                "modifier_data": serialized,
                "modifier_json": json.dumps(serialized),
                "behavior_choices": behavior_choices,
            },
        )
        response["HX-Trigger"] = json.dumps(trigger)
        return response

    serialized = _modifier_payload(modifiers)
    context = {
        "modifiers": modifiers,
        "ingredients": ingredients,
        "ingredient_types": ingredient_types,
        "modifier_data": serialized,
        "modifier_json": json.dumps(serialized),
        "behavior_choices": behavior_choices,
    }
    return render(request, "modifiers/rules_modal.html", context)

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
