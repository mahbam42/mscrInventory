import datetime
from decimal import Decimal

from django.conf import settings
from django.shortcuts import render
from django.utils import timezone

from mscrInventory.models import IngredientUsageLog
from mscrInventory.utils import reports


def _parse_date(value: str | None) -> datetime.date | None:
    if not value:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return None


def reporting_dashboard_view(request):
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
    top_products = reports.top_selling_products(start, end)
    top_modifiers = reports.top_modifiers(start, end)

    total_cogs = sum((row["cogs"] for row in product_summary), Decimal("0"))
    total_revenue = sum((row["revenue"] for row in product_summary), Decimal("0"))

    usage_logs = (
        IngredientUsageLog.objects
        .select_related("ingredient")
        .filter(date__gte=start, date__lte=end)
        .order_by("-date", "ingredient__name")
    )

    context = {
        "start": start,
        "end": end,
        "product_summary": product_summary,
        "category_summary": category_summary,
        "profitability": profitability,
        "trend": trend,
        "usage_totals": sorted(usage_totals.items()),
        "usage_logs": usage_logs,
        "linkage": linkage,
        "top_products": top_products,
        "top_modifiers": top_modifiers,
        "total_cogs": total_cogs,
        "total_revenue": total_revenue,
        "tzname": tzname,
    }

    return render(request, "reports/dashboard.html", context)
