from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from mscrInventory.utils.dashboard_metrics import (
    build_stat_cards,
    get_activity_feed,
    get_low_stock_summary,
    get_quick_actions,
    get_recent_imports,
    get_shortcuts,
    get_stat_counts,
    get_warning_items,
)


def dashboard_view(request: HttpRequest) -> HttpResponse:
    low_stock_summary = get_low_stock_summary()
    stat_counts = get_stat_counts()
    stat_cards = build_stat_cards(stat_counts, low_stock_summary)
    recent_imports = get_recent_imports()

    context = {
        "stat_cards": stat_cards,
        "recent_imports": recent_imports,
        "activity_feed": get_activity_feed(),
        "quick_actions": get_quick_actions(),
        "warnings": get_warning_items(low_stock_summary, stat_counts, recent_imports),
        "shortcuts": get_shortcuts(),
    }
    return render(request, "dashboard.html", context)

