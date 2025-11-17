"""Reporting helpers for COGS, usage, and profitability dashboards."""
from __future__ import annotations
import datetime
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, List, Tuple

from django.db.models import Sum, F, Q
from django.utils import timezone

from ..models import (
    Ingredient,
    IngredientUsageLog,
    OrderItem,
    Product,
    RecipeModifier,
    StockEntry,
)


SIZE_DESCRIPTOR_TOKENS: set[str] = {
    "kids",
    "kid",
    "small",
    "medium",
    "large",
    "xl",
    "xxl",
    "short",
    "tall",
    "grande",
    "venti",
    "trenta",
}
TEMP_DESCRIPTOR_TOKENS: set[str] = {
    "hot",
    "iced",
    "extra hot",
    "cold",
    "warm",
    "room temperature",
}
SUPPRESSED_DESCRIPTOR_TOKENS: set[str] = SIZE_DESCRIPTOR_TOKENS | TEMP_DESCRIPTOR_TOKENS
IGNORED_MODIFIER_TOKENS: set[str] = {"regular"}


def _normalize_descriptor_token(token: str | None) -> str:
    """Lowercase and strip descriptor tokens for deduping."""
    return (token or "").strip().lower()


def _split_descriptor_tokens(tokens: Iterable[str] | None) -> tuple[list[str], list[str]]:
    """Return (kept_tokens, suppressed_tokens) preserving first-seen casing."""

    kept: dict[str, str] = {}
    suppressed: dict[str, str] = {}
    for token in tokens or []:
        normalized = _normalize_descriptor_token(token)
        if not normalized:
            continue
        bucket = suppressed if normalized in SUPPRESSED_DESCRIPTOR_TOKENS else kept
        bucket.setdefault(normalized, token)
    return list(kept.values()), list(suppressed.values())


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
            "date_obj": cur,
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
            allocations = [("Uncategorized", Decimal("1"))]
        else:
            share = Decimal("1") / Decimal(len(categories))
            allocations = [(category.name, share) for category in categories]
        for category_name, weight in allocations:
            bucket = category_totals[category_name]
            bucket["quantity"] += row["quantity"] * weight
            bucket["revenue"] += row["revenue"] * weight
            bucket["cogs"] += row["cogs"] * weight

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
        if "date_obj" not in row:
            try:
                row["date_obj"] = datetime.date.fromisoformat(row["date"])
            except (TypeError, ValueError):
                row["date_obj"] = None
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


def _unique_preserving_order(tokens: Iterable[str]) -> list[str]:
    """Normalize tokens to deduplicate while retaining first-seen casing."""

    seen: set[str] = set()
    ordered: list[str] = []
    for token in tokens:
        normalized = _normalize_descriptor_token(token)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(token)
    return ordered


def top_selling_products(start: datetime.date, end: datetime.date, *, limit: int = 10) -> List[Dict]:
    """Return top-selling products aggregated by base product with variant breakdowns."""

    items = (
        OrderItem.objects
        .select_related("product", "order")
        .filter(order__order_date__date__gte=start, order__order_date__date__lte=end)
    )

    totals: Dict[
        Tuple[int | None, str],
        Dict[str, object],
    ] = {}

    def _ensure_bucket(key: Tuple[int | None, str], display_name: str):
        bucket = totals.get(key)
        if bucket is None:
            bucket = {
                "product_name": display_name,
                "adjectives": {},
                "modifiers": {},
                "suppressed_descriptors": {},
                "quantity": Decimal("0"),
                "gross_sales": Decimal("0"),
                "variant_details": {},
            }
            totals[key] = bucket
        return bucket

    for item in items:
        product = item.product
        qty = Decimal(item.quantity or 0)
        revenue = (item.unit_price or Decimal("0")) * qty
        info = item.variant_info or {}

        adjectives_raw = info.get("adjectives") or []
        modifiers_raw = info.get("modifiers") or []

        kept_adjectives, suppressed_adjectives = _split_descriptor_tokens(adjectives_raw)
        kept_modifiers, suppressed_modifiers = _split_descriptor_tokens(modifiers_raw)
        kept_modifiers = [
            token
            for token in kept_modifiers
            if _normalize_descriptor_token(token) not in IGNORED_MODIFIER_TOKENS
        ]

        size_token = info.get("size")
        temp_token = info.get("temp_type")
        meta_suppressed: list[str] = []
        for token in (size_token, temp_token):
            normalized = _normalize_descriptor_token(token)
            if normalized:
                if normalized in SUPPRESSED_DESCRIPTOR_TOKENS:
                    meta_suppressed.append(token)
                else:
                    kept_adjectives.append(token)

        canonical_product = (product.name if product else info.get("name") or "Unmapped").strip() or "Unmapped"
        product_key = getattr(product, "id", None)
        bucket_key = (product_key, canonical_product.lower())
        bucket = _ensure_bucket(bucket_key, canonical_product)

        def _capture(tokens: Iterable[str], storage: dict[str, str]):
            for token in tokens:
                normalized = _normalize_descriptor_token(token)
                if not normalized:
                    continue
                storage.setdefault(normalized, token)

        _capture(kept_adjectives, bucket["adjectives"])
        _capture(kept_modifiers, bucket["modifiers"])
        _capture(suppressed_adjectives, bucket["suppressed_descriptors"])
        _capture(suppressed_modifiers, bucket["suppressed_descriptors"])
        _capture(meta_suppressed, bucket["suppressed_descriptors"])

        bucket["quantity"] += qty
        bucket["gross_sales"] += revenue

        normalized_adjectives = tuple(sorted({
            _normalize_descriptor_token(token)
            for token in kept_adjectives
            if _normalize_descriptor_token(token)
        }))
        normalized_modifiers = tuple(sorted({
            _normalize_descriptor_token(token)
            for token in kept_modifiers
            if _normalize_descriptor_token(token)
        }))
        normalized_suppressed = tuple(sorted({
            _normalize_descriptor_token(token)
            for token in list(suppressed_adjectives) + list(suppressed_modifiers) + list(meta_suppressed)
            if _normalize_descriptor_token(token)
        }))

        variant_key = (normalized_adjectives, normalized_modifiers, normalized_suppressed)
        variant_bucket = bucket["variant_details"].get(variant_key)
        if variant_bucket is None:
            variant_bucket = {
                "adjectives": tuple(_unique_preserving_order(kept_adjectives)),
                "modifiers": tuple(_unique_preserving_order(kept_modifiers)),
                "suppressed_descriptors": tuple(_unique_preserving_order(list(suppressed_adjectives) + list(suppressed_modifiers) + list(meta_suppressed))),
                "quantity": Decimal("0"),
                "gross_sales": Decimal("0"),
            }
            bucket["variant_details"][variant_key] = variant_bucket

        variant_bucket["quantity"] += qty
        variant_bucket["gross_sales"] += revenue

    rows: List[Dict] = []
    for payload in totals.values():
        variant_details = list(payload["variant_details"].values())
        variant_details.sort(key=lambda row: (row["quantity"], row["gross_sales"]), reverse=True)

        rows.append({
            "product_name": payload["product_name"],
            "adjectives": tuple(sorted(payload["adjectives"].values(), key=str.lower)),
            "modifiers": tuple(sorted(payload["modifiers"].values(), key=str.lower)),
            "suppressed_descriptors": tuple(sorted(payload["suppressed_descriptors"].values(), key=str.lower)),
            "quantity": payload["quantity"],
            "gross_sales": payload["gross_sales"],
            "variant_count": len(variant_details),
            "variant_details": tuple(variant_details),
        })

    rows.sort(key=lambda row: (row["quantity"], row["gross_sales"]), reverse=True)
    return rows[:limit]


def top_modifiers(start: datetime.date, end: datetime.date, *, limit: int = 10) -> List[Dict]:
    """Return the most frequently used modifiers with friendly ingredient labels."""

    items = (
        OrderItem.objects
        .select_related("order")
        .filter(order__order_date__date__gte=start, order__order_date__date__lte=end)
    )

    modifier_totals: Dict[str, Dict[str, object]] = {}

    for item in items:
        qty = Decimal(item.quantity or 0)
        revenue = (item.unit_price or Decimal("0")) * qty
        info = item.variant_info or {}
        modifiers = set(info.get("modifiers") or [])
        for modifier in modifiers:
            normalized = _normalize_descriptor_token(modifier)
            if (
                not normalized
                or normalized in SUPPRESSED_DESCRIPTOR_TOKENS
                or normalized in IGNORED_MODIFIER_TOKENS
            ):
                continue
            bucket = modifier_totals.setdefault(
                normalized,
                {
                    "quantity": Decimal("0"),
                    "gross_sales": Decimal("0"),
                    "raw_labels": set(),
                },
            )
            bucket["quantity"] += qty
            bucket["gross_sales"] += revenue
            bucket["raw_labels"].add(modifier)

    if not modifier_totals:
        return []

    raw_names = {label for bucket in modifier_totals.values() for label in bucket["raw_labels"]}
    modifier_qs = (
        RecipeModifier.objects
        .select_related("ingredient", "ingredient__unit_type")
        .filter(Q(name__in=raw_names) | Q(ingredient__name__in=raw_names))
    )

    resolved_modifiers: Dict[str, RecipeModifier] = {}
    for rm in modifier_qs:
        resolved_modifiers[_normalize_descriptor_token(rm.name)] = rm
        if rm.ingredient:
            resolved_modifiers[_normalize_descriptor_token(rm.ingredient.name)] = rm

    rows = []
    for normalized_name, payload in modifier_totals.items():
        raw_labels = sorted(payload["raw_labels"], key=str.lower)
        modifier_obj = resolved_modifiers.get(normalized_name)
        if not modifier_obj:
            for label in raw_labels:
                modifier_obj = resolved_modifiers.get(_normalize_descriptor_token(label))
                if modifier_obj:
                    break

        display_name = raw_labels[0] if raw_labels else normalized_name
        unit = None
        if modifier_obj:
            if modifier_obj.ingredient:
                display_name = modifier_obj.ingredient.name
                unit_type = getattr(modifier_obj.ingredient, "unit_type", None)
                unit = modifier_obj.unit or getattr(unit_type, "abbreviation", None) or getattr(unit_type, "name", None)
            else:
                display_name = modifier_obj.name
                unit = modifier_obj.unit

        rows.append({
            "modifier": display_name,
            "original_label": raw_labels[0] if raw_labels else None,
            "unit": unit,
            "quantity": payload["quantity"],
            "gross_sales": payload["gross_sales"],
        })

    rows.sort(key=lambda row: (row["quantity"], row["gross_sales"]), reverse=True)
    return rows[:limit]
