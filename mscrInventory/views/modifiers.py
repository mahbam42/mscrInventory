from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from mscrInventory.models import RecipeModifier

def edit_modifier_extra_view(request, modifier_id):
    modifier = get_object_or_404(RecipeModifier, pk=modifier_id)
    # stub logic for now
    return JsonResponse({"status": "ok", "modifier": modifier.name})
