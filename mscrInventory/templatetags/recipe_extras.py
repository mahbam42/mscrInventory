from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django import template
from django.http import QueryDict
from django.utils.html import format_html

register = template.Library()


@register.filter
def get_item(mapping: Any, key: Any) -> Any:
    try:
        return mapping.get(key)
    except Exception:
        return None


@register.filter
def multiply(value: Any, other: Any) -> Any:
    if value is None or other is None:
        return None
    try:
        return Decimal(value) * Decimal(other)
    except (InvalidOperation, TypeError):
        try:
            return value * other
        except Exception:
            return None


@register.simple_tag(takes_context=True)
def sort_url(context: dict, column: str) -> str:
    request = context.get("request")
    if request is None:
        return "?"

    params: QueryDict = request.GET.copy()
    params["sort"] = column

    current_sort = context.get("sort", "order_date")
    current_direction = context.get("direction", "desc")
    next_direction = "desc" if current_sort == column and current_direction == "asc" else "asc"
    params["direction"] = next_direction
    params.pop("page", None)

    query = params.urlencode()
    return f"?{query}" if query else "?"


@register.simple_tag
def sort_indicator(current_sort: str, current_direction: str, column: str) -> str:
    if current_sort != column:
        return ""
    is_ascending = current_direction == "asc"
    arrow = "↑" if is_ascending else "↓"
    direction_label = "ascending" if is_ascending else "descending"
    return format_html(
        '<span class="ms-1" aria-hidden="true">{}</span>'
        '<span class="visually-hidden">sorted {}</span>',
        arrow,
        direction_label,
    )
