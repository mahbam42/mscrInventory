from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Dict, Optional

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.http import urlencode

from mscrInventory.models import Order


@dataclass
class DateRange:
    start: datetime
    end: datetime
    start_date: date
    end_date: date


_PRESET_WINDOWS: Dict[str, int] = {
    "7": 7,
    "14": 14,
    "30": 30,
    "90": 90,
}


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _resolve_date_range(preset: str, start_param: Optional[str], end_param: Optional[str]) -> DateRange:
    today = timezone.localdate()
    end_date = _parse_date(end_param) or today

    if preset != "custom" and preset in _PRESET_WINDOWS:
        days = _PRESET_WINDOWS[preset]
        start_date = end_date - timedelta(days=days - 1)
    else:
        parsed_start = _parse_date(start_param)
        start_date = parsed_start or (end_date - timedelta(days=_PRESET_WINDOWS["14"] - 1))

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(start_date, time.min), timezone=tz)
    end_dt = timezone.make_aware(datetime.combine(end_date, time.max), timezone=tz)
    return DateRange(start=start_dt, end=end_dt, start_date=start_date, end_date=end_date)


@login_required
def orders_dashboard_view(request: HttpRequest) -> HttpResponse:
    preset = request.GET.get("preset", "14")
    platform = request.GET.get("platform", "all")
    date_range = _resolve_date_range(preset, request.GET.get("start"), request.GET.get("end"))

    orders_qs = (
        Order.objects.filter(order_date__range=(date_range.start, date_range.end))
        .annotate(total_items=Coalesce(Sum("items__quantity"), 0))
        .prefetch_related("items", "items__product")
        .order_by("-order_date")
    )
    if platform and platform.lower() != "all":
        orders_qs = orders_qs.filter(platform__iexact=platform)

    paginator = Paginator(orders_qs, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    preserved_params = request.GET.copy()
    preserved_params.pop("page", None)
    querystring = urlencode({k: v for k, v in preserved_params.items() if v})

    context = {
        "page_obj": page_obj,
        "orders": page_obj.object_list,
        "selected_preset": preset if preset in _PRESET_WINDOWS or preset == "custom" else "14",
        "selected_platform": platform.lower() if platform else "all",
        "start_date": date_range.start_date,
        "end_date": date_range.end_date,
        "show_custom_range": preset == "custom",
        "querystring": f"&{querystring}" if querystring else "",
        "preset_options": [
            ("7", "Last 7 days"),
            ("14", "Last 14 days"),
            ("30", "Last 30 days"),
            ("90", "Last 90 days"),
            ("custom", "Custom"),
        ],
        "platform_options": [
            ("all", "All Platforms"),
            ("shopify", "Shopify"),
            ("square", "Square"),
        ],
    }
    return render(request, "orders/dashboard.html", context)
