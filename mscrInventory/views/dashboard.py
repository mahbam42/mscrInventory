"""Views that render the executive dashboard."""

from django.contrib.auth.decorators import login_required
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
    get_top_named_drinks,
    get_warning_items,
    NAMED_DRINK_LOOKBACK_DAYS,
)


@login_required
def dashboard_view(request: HttpRequest) -> HttpResponse:
    """Render dashboard cards, stats, warnings, and quick actions."""
    role = (
        request.user.groups.first().name
        if request.user.groups.exists()
        else "Unassigned"
    )
    low_stock_summary = get_low_stock_summary()
    stat_counts = get_stat_counts()
    stat_cards = build_stat_cards(stat_counts, low_stock_summary)
    recent_imports = get_recent_imports()

    context = {
        "stat_cards": stat_cards,
        "recent_imports": recent_imports,
        "activity_feed": get_activity_feed(),
        "quick_actions": get_quick_actions(),
        "named_drinks": get_top_named_drinks(),
        "named_drinks_window": NAMED_DRINK_LOOKBACK_DAYS,
        "warnings": get_warning_items(low_stock_summary, stat_counts, recent_imports),
        "shortcuts": get_shortcuts(),
        "user_role": role,
    }
    return render(request, "dashboard.html", context)
