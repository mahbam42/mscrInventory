"""Reporting dashboards for COGS, usage, and profitability."""

import datetime
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render
from django.utils import timezone

from mscrInventory.models import IngredientUsageLog, SquareUnmappedItem
from mscrInventory.utils import reports


def _parse_date(value: str | None) -> datetime.date | None:
    """Return parsed ISO8601 date or None on error."""
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def _quick_date_ranges(today: datetime.date) -> list[dict[str, str]]:
    """Return quick date range presets anchored to today's date."""

    start_of_week = today - datetime.timedelta(days=today.weekday())
    start_of_last_week = start_of_week - datetime.timedelta(days=7)
    end_of_last_week = start_of_week - datetime.timedelta(days=1)

    start_of_month = today.replace(day=1)
    end_of_last_month = start_of_month - datetime.timedelta(days=1)
    start_of_last_month = end_of_last_month.replace(day=1)

    start_of_year = today.replace(month=1, day=1)
    end_of_last_year = start_of_year - datetime.timedelta(days=1)
    start_of_last_year = end_of_last_year.replace(month=1, day=1)

    def _range(key: str, label: str, start: datetime.date, end: datetime.date) -> dict[str, str]:
        return {"key": key, "label": label, "start": start.isoformat(), "end": end.isoformat()}

    return [
        _range("today", "Today", today, today),
        _range("yesterday", "Yesterday", today - datetime.timedelta(days=1), today - datetime.timedelta(days=1)),
        _range("this_week", "This Week", start_of_week, today),
        _range("last_week", "Last Week", start_of_last_week, end_of_last_week),
        _range("this_month", "This Month", start_of_month, today),
        _range("last_month", "Last Month", start_of_last_month, end_of_last_month),
        _range("this_year", "This Year", start_of_year, today),
        _range("last_year", "Last Year", start_of_last_year, end_of_last_year),
    ]


@permission_required("mscrInventory.change_order", raise_exception=True)
@login_required
def reporting_dashboard_view(request):
    """Render the reporting dashboard with aggregates and raw usage logs."""
    today = timezone.localdate()
    default_start = today - datetime.timedelta(days=6)
    start = _parse_date(request.GET.get("start")) or default_start
    end = _parse_date(request.GET.get("end")) or today
    if end < start:
        start, end = end, start

    tzname = getattr(settings, "SYNC_TIMEZONE", "America/New_York")

    product_summary = reports.cogs_summary_by_product(start, end)
    category_summary = reports.cogs_summary_by_category(start, end)
    profitability = reports.category_profitability(start, end)
    trend = reports.cogs_trend_with_variance(start, end, tzname=tzname)
    usage_totals = reports.aggregate_usage_totals(start, end)
    linkage = reports.validate_cogs_linkage(start, end)
    top_products = reports.top_selling_products_with_changes(start, end)
    top_modifiers = reports.top_modifiers_with_changes(start, end)

    total_cogs = sum((row["cogs"] for row in product_summary), Decimal("0"))
    total_revenue = sum((row["revenue"] for row in product_summary), Decimal("0"))

    usage_logs = (
        IngredientUsageLog.objects
        .select_related("ingredient", "ingredient__unit_type")
        .filter(date__gte=start, date__lte=end)
        .order_by("-date", "ingredient__name")
    )
    unresolved_count = SquareUnmappedItem.objects.filter(resolved=False, ignored=False).count()

    context = {
        "start": start,
        "end": end,
        "product_summary": product_summary,
        "category_summary": category_summary,
        "profitability": profitability,
        "trend": trend,
        "usage_totals": usage_totals,
        "usage_logs": usage_logs,
        "linkage": linkage,
        "top_products": top_products,
        "top_modifiers": top_modifiers,
        "total_cogs": total_cogs,
        "total_revenue": total_revenue,
        "tzname": tzname,
        "unresolved_count": unresolved_count,
        "quick_date_ranges": _quick_date_ranges(today),
    }

    return render(request, "reports/dashboard.html", context)
