# yourapp/utils/reports.py
from __future__ import annotations
import datetime
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, List, Tuple

from django.db.models import Sum, F
from django.utils import timezone

from ..models import (
    Ingredient,
    IngredientUsageLog,
    OrderItem,
    Product,
    StockEntry,
)


def daterange(start: datetime.date, end: datetime.date) -> Iterable[datetime.date]:
    """Yield every date between start and end inclusive."""

    current = start
    while current <= end:
        yield current
        current += datetime.timedelta(days=1)


def _day_window_utc(day: datetime.date, tzname: str = "America/New_York") -> Tuple[datetime.datetime, datetime.datetime]:
    """Inclusive day window in UTC for a local business day."""
    import pytz
    tz = pytz.timezone(tzname)
    start_local = tz.localize(datetime.datetime.combine(day, datetime.time.min))
    end_local = tz.localize(datetime.datetime.combine(day, datetime.time.max))
    return start_local.astimezone(datetime.timezone.utc), end_local.astimezone(datetime.timezone.utc)


def average_cost_as_of_date(ingredient_id: int, day: datetime.date) -> Decimal:
    """
    Weighted average cost for an ingredient based on StockEntries <= end of 'day'.
    If no stock exists yet, returns Decimal('0').
    """
    start_utc, end_utc = _day_window_utc(day)
    agg = (StockEntry.objects
           .filter(ingredient_id=ingredient_id, date_received__lte=end_utc)
           .aggregate(
               qty=Sum('quantity_added'),
               cost=Sum(F('quantity_added') * F('cost_per_unit'))
           ))
    qty = agg['qty'] or Decimal(0)
    cost = agg['cost'] or Decimal(0)
    if qty <= 0:
        return Decimal("0")
    return (cost / qty).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def cogs_for_day(day: datetime.date, tzname: str = "America/New_York") -> Dict[str, Decimal]:
    """
    Returns a mapping:
        {
          "cogs_total": Decimal,
          "per_ingredient": {ingredient_name: {"qty_used": Decimal, "unit_cost": Decimal, "cogs": Decimal}}
        }
    Uses IngredientUsageLog entries on that day, multiplied by each ingredient's weighted
    average cost as of that day.
    """
    start_utc, end_utc = _day_window_utc(day, tzname)

    # Usage on that business day
    usage = (IngredientUsageLog.objects
             .select_related("ingredient")
             .filter(date=day)
             .values("ingredient_id", "ingredient__name")
             .annotate(qty_used=Sum("quantity_used"))
             .order_by("ingredient__name"))

    per_ing = {}
    total = Decimal("0")
    for row in usage:
        ing_id = row["ingredient_id"]
        name = row["ingredient__name"]
        qty = row["qty_used"] or Decimal(0)
        unit_cost = average_cost_as_of_date(ing_id, day)
        cogs = (qty * unit_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        per_ing[name] = {
            "qty_used": qty.quantize(Decimal("0.001")),
            "unit_cost": unit_cost,
            "cogs": cogs,
        }
        total += cogs

    return {"cogs_total": total, "per_ingredient": per_ing}


def cogs_by_day(start: datetime.date, end: datetime.date, tzname: str = "America/New_York") -> List[Dict]:
    """
    Inclusive date range. Returns a list of dict rows:
      [{"date": YYYY-MM-DD, "cogs_total": Decimal}, ...]
    """
    rows = []
    cur = start
    while cur <= end:
        day_data = cogs_for_day(cur, tzname)
        rows.append({
            "date": cur.isoformat(),
            "cogs_total": day_data["cogs_total"],
        })
        cur += datetime.timedelta(days=1)
    return rows


def usage_detail_by_day(start: datetime.date, end: datetime.date) -> List[Dict]:
    """
    Returns detailed rows suitable for CSV:
      date, ingredient, qty_used, unit_cost_as_of_day, cogs
    """
    out: List[Dict] = []
    cur = start
    while cur <= end:
        # Aggregate all usage logs for the day by ingredient
        day_rows = (IngredientUsageLog.objects
                    .select_related("ingredient")
                    .filter(date=cur)
                    .values("ingredient_id", "ingredient__name")
                    .annotate(qty_used=Sum("quantity_used"))
                    .order_by("ingredient__name"))
        for r in day_rows:
            unit_cost = average_cost_as_of_date(r["ingredient_id"], cur)
            qty = r["qty_used"] or Decimal(0)
            cogs = (qty * unit_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            out.append({
                "date": cur.isoformat(),
                "ingredient": r["ingredient__name"],
                "qty_used": qty.quantize(Decimal("0.001")),
                "unit_cost": unit_cost,
                "cogs": cogs,
            })
        cur += datetime.timedelta(days=1)
    return out


def cogs_summary_by_product(start: datetime.date, end: datetime.date) -> List[Dict]:
    """Aggregate COGS totals per product (recipe) for the date range."""

    items = (
        OrderItem.objects
        .select_related("product", "order")
        .filter(order__order_date__date__gte=start, order__order_date__date__lte=end, product__isnull=False)
    )

    summary: Dict[int, Dict[str, Decimal | str | int]] = {}
    for item in items:
        if not item.product:
            continue
        product = item.product
        qty = Decimal(item.quantity or 0)
        revenue = (item.unit_price or Decimal("0")) * qty
        cogs = product.calculated_cogs * qty

        data = summary.setdefault(
            product.id,
            {
                "product": product,
                "product_name": product.name,
                "sku": product.sku,
                "product_id": product.id,
                "quantity": Decimal("0"),
                "revenue": Decimal("0"),
                "cogs": Decimal("0"),
            },
        )
        data["quantity"] += qty
        data["revenue"] += revenue
        data["cogs"] += cogs

    rows = []
    for payload in summary.values():
        profit = payload["revenue"] - payload["cogs"]
        margin = Decimal("0")
        if payload["revenue"]:
            margin = (profit / payload["revenue"]) * Decimal("100")
        rows.append({
            "product_name": payload["product_name"],
            "sku": payload["sku"],
            "product_id": payload["product_id"],
            "quantity": payload["quantity"],
            "revenue": payload["revenue"],
            "cogs": payload["cogs"],
            "profit": profit,
            "margin_pct": margin.quantize(Decimal("0.01")) if payload["revenue"] else None,
        })

    rows.sort(key=lambda row: row["cogs"], reverse=True)
    return rows


def cogs_summary_by_category(start: datetime.date, end: datetime.date) -> List[Dict]:
    """Aggregate COGS totals per category for the date range."""

    product_rows = cogs_summary_by_product(start, end)
    product_ids = [row["product_id"] for row in product_rows if row.get("product_id")]
    product_qs = (
        Product.objects.filter(id__in=product_ids)
        .prefetch_related("categories")
    )
    product_map = {product.id: product for product in product_qs}
    category_totals: Dict[str, Dict[str, Decimal]] = defaultdict(lambda: {
        "quantity": Decimal("0"),
        "revenue": Decimal("0"),
        "cogs": Decimal("0"),
    })

    for row in product_rows:
        product = product_map.get(row.get("product_id")) if row.get("product_id") else None
        categories = list(product.categories.all()) if product else []
        if not categories:
            category_names = ["Uncategorized"]
        else:
            category_names = [category.name for category in categories]
        for category_name in category_names:
            bucket = category_totals[category_name]
            bucket["quantity"] += row["quantity"]
            bucket["revenue"] += row["revenue"]
            bucket["cogs"] += row["cogs"]

    results: List[Dict] = []
    for name, payload in category_totals.items():
        profit = payload["revenue"] - payload["cogs"]
        margin = Decimal("0")
        if payload["revenue"]:
            margin = (profit / payload["revenue"]) * Decimal("100")
        results.append({
            "category": name,
            "quantity": payload["quantity"],
            "revenue": payload["revenue"],
            "cogs": payload["cogs"],
            "profit": profit,
            "margin_pct": margin.quantize(Decimal("0.01")) if payload["revenue"] else None,
        })

    results.sort(key=lambda row: row["cogs"], reverse=True)
    return results


def category_profitability(start: datetime.date, end: datetime.date) -> Dict[str, Decimal]:
    """Return high-level profitability metrics for the selected date range."""

    product_rows = cogs_summary_by_product(start, end)
    overall_revenue = sum((row["revenue"] for row in product_rows), Decimal("0"))
    overall_cogs = sum((row["cogs"] for row in product_rows), Decimal("0"))
    overall_profit = overall_revenue - overall_cogs
    margin_pct = Decimal("0")
    if overall_revenue:
        margin_pct = (overall_profit / overall_revenue) * Decimal("100")

    return {
        "overall_revenue": overall_revenue,
        "overall_cogs": overall_cogs,
        "overall_profit": overall_profit,
        "overall_margin_pct": margin_pct.quantize(Decimal("0.01")) if overall_revenue else None,
    }


def cogs_trend_with_variance(start: datetime.date, end: datetime.date, tzname: str = "America/New_York") -> List[Dict]:
    """Return daily totals with variance data compared to the previous day."""

    trend = cogs_by_day(start, end, tzname=tzname)
    previous_total: Decimal | None = None
    for row in trend:
        total = row["cogs_total"]
        if previous_total is None:
            row["variance"] = None
            row["variance_pct"] = None
        else:
            variance = total - previous_total
            row["variance"] = variance
            if previous_total:
                row["variance_pct"] = (variance / previous_total * Decimal("100")).quantize(Decimal("0.01"))
            else:
                row["variance_pct"] = None
        previous_total = total
    return trend


def aggregate_usage_totals(start: datetime.date, end: datetime.date) -> Dict[str, Decimal]:
    """Aggregate ingredient usage quantities for the date range."""

    totals: Dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    logs = (
        IngredientUsageLog.objects
        .select_related("ingredient")
        .filter(date__gte=start, date__lte=end)
    )
    for log in logs:
        totals[log.ingredient.name] += Decimal(log.quantity_used)
    return dict(totals)


def validate_cogs_linkage(start: datetime.date, end: datetime.date) -> Dict[str, List[str]]:
    """Identify ingredients without cost data within the usage window."""

    missing_cost: set[str] = set()
    logs = (
        IngredientUsageLog.objects
        .select_related("ingredient")
        .filter(date__gte=start, date__lte=end)
    )
    for log in logs:
        cost = log.ingredient.average_cost_per_unit or Decimal("0")
        if cost <= 0:
            missing_cost.add(log.ingredient.name)

    return {"missing_cost_ingredients": sorted(missing_cost)}


def top_selling_products(start: datetime.date, end: datetime.date, *, limit: int = 10) -> List[Dict]:
    """Return top-selling product variants including descriptor context."""

    items = (
        OrderItem.objects
        .select_related("product", "order")
        .filter(order__order_date__date__gte=start, order__order_date__date__lte=end)
    )

    totals: Dict[Tuple[int | None, Tuple[str, ...], Tuple[str, ...]], Dict[str, Decimal | str]] = {}
    for item in items:
        product = item.product
        qty = Decimal(item.quantity or 0)
        revenue = (item.unit_price or Decimal("0")) * qty
        info = item.variant_info or {}
        adjectives = tuple(sorted(set(info.get("adjectives") or [])))
        modifiers = tuple(sorted(set(info.get("modifiers") or [])))
        key = (getattr(product, "id", None), adjectives, modifiers)

        display_name = product.name if product else info.get("name") or "Unmapped"
        totals.setdefault(
            key,
            {
                "product_name": display_name,
                "adjectives": adjectives,
                "modifiers": modifiers,
                "quantity": Decimal("0"),
                "gross_sales": Decimal("0"),
            },
        )
        totals[key]["quantity"] += qty
        totals[key]["gross_sales"] += revenue

    rows = list(totals.values())
    rows.sort(key=lambda row: (row["quantity"], row["gross_sales"]), reverse=True)
    return rows[:limit]


def top_modifiers(start: datetime.date, end: datetime.date, *, limit: int = 10) -> List[Dict]:
    """Return the most frequently used modifiers within the date range."""

    items = (
        OrderItem.objects
        .select_related("order")
        .filter(order__order_date__date__gte=start, order__order_date__date__lte=end)
    )

    modifier_totals: Dict[str, Dict[str, Decimal]] = defaultdict(lambda: {
        "quantity": Decimal("0"),
        "gross_sales": Decimal("0"),
    })

    for item in items:
        qty = Decimal(item.quantity or 0)
        revenue = (item.unit_price or Decimal("0")) * qty
        info = item.variant_info or {}
        modifiers = set(info.get("modifiers") or [])
        for modifier in modifiers:
            bucket = modifier_totals[modifier]
            bucket["quantity"] += qty
            bucket["gross_sales"] += revenue

    rows = [
        {
            "modifier": name,
            "quantity": payload["quantity"],
            "gross_sales": payload["gross_sales"],
        }
        for name, payload in modifier_totals.items()
    ]
    rows.sort(key=lambda row: (row["quantity"], row["gross_sales"]), reverse=True)
    return rows[:limit]
