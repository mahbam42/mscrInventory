# yourapp/management/commands/sync_orders.py
import os
import requests
from decimal import Decimal

import datetime
from zoneinfo import ZoneInfo
import datetime
from collections import defaultdict
from decimal import Decimal
from typing import Iterable, Dict, Any, List, Tuple

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from ...models import (
    Product, Ingredient, RecipeItem,
    Order, OrderItem, IngredientUsageLog
)

# ---------------------------
# Helpers
# ---------------------------

# def nyc_day_window(target_date: datetime.date) -> Tuple[datetime.datetime, datetime.datetime]:
#    """Return start/end datetimes for the cafe day in America/New_York."""
#    tz = timezone.pytz.timezone(getattr(settings, "SYNC_TIMEZONE", "America/New_York"))
#    start = tz.localize(datetime.datetime.combine(target_date, datetime.time.min)).astimezone(timezone.utc)
#    end = tz.localize(datetime.datetime.combine(target_date, datetime.time.max)).astimezone(timezone.utc)
#    return start, end

def nyc_day_window(target_date: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    tz = ZoneInfo(getattr(settings, "SYNC_TIMEZONE", "America/New_York"))
    start_local = datetime.datetime.combine(target_date, datetime.time.min, tzinfo=tz)
    end_local   = datetime.datetime.combine(target_date, datetime.time.max, tzinfo=tz)
    # Convert to UTC datetimes
    return start_local.astimezone(datetime.timezone.utc), end_local.astimezone(datetime.timezone.utc)

def to_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))

def _json_safe(value):
    import datetime, decimal
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value

# Old Version - the above function should correct 
#def _json_safe(value):
#    import datetime
#    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
#        return value.isoformat()
#    if isinstance(value, dict):
#        return {k: _json_safe(v) for k, v in value.items()}
#    if isinstance(value, list):
#        return [_json_safe(v) for v in value]
#    return value

# ---------------------------
# Shopify fetch (placeholder)
# ---------------------------

def fetch_shopify_orders(start_utc: datetime.datetime, end_utc: datetime.datetime) -> List[Dict[str, Any]]:
    """
    Fetch orders from Shopify REST API between the given UTC datetimes.
    Returns normalized list of orders:
    [
      {
        "order_id": str,
        "order_date": datetime,
        "total_amount": Decimal,
        "items": [{"sku_or_handle": str, "quantity": int, "unit_price": Decimal}],
      },
      ...
    ]
    """
    api_key = os.getenv("SHOPIFY_API_KEY")
    password = os.getenv("SHOPIFY_PASSWORD")
    store_domain = os.getenv("SHOPIFY_STORE_DOMAIN")
    if not (api_key and password and store_domain):
        print("⚠️ Shopify credentials not set; skipping fetch.")
        return []

    url = f"https://{store_domain}/admin/api/2024-10/orders.json"

    params = {
        "status": "any",
        "financial_status": "any",
        "fulfillment_status": "any",
        "created_at_min": start_utc.isoformat().replace("+00:00", "Z"),
        "created_at_max": end_utc.isoformat().replace("+00:00", "Z"),
        "limit": 250,
        "fields": "id,created_at,total_price,line_items",
    }

    try:
        resp = requests.get(url, auth=(api_key, password), params=params, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"❌ Shopify API error: {e}")
        return []

    data = resp.json()
    orders = data.get("orders", [])
    normalized = []

    for o in orders:
        order_id = str(o["id"])
        order_date = datetime.datetime.fromisoformat(o["created_at"].replace("Z", "+00:00"))
        total_amount = Decimal(o["total_price"])
        items = []
        for li in o.get("line_items", []):
            sku = li.get("sku")
            title = li.get("title") or ""
            if title and "(" in title and title.endswith(f"({sku})"):
                # Strip redundant (SKU)
                title = title[:title.rfind("(")].strip()

            name = li.get("name") or ""
            variant_title = li.get("variant_title") or ""

            # Choose SKU if present; otherwise fall back to the cleanest display name
            sku_or_handle = sku or (title if title else name)
            
            # sku_or_handle = li.get("sku") or li.get("title")
            # ^^ old line ^^ 
            quantity = int(li["quantity"])
            unit_price = Decimal(li["price"])
            items.append({
                "sku_or_handle": sku_or_handle,
                "quantity": quantity,
                "unit_price": unit_price,
            })
        normalized.append({
            "order_id": order_id,
            "order_date": order_date,
            "total_amount": total_amount,
            "items": items,
        })

    print(f"✅ Shopify orders fetched: {len(normalized)}")
    return normalized

# ---------------------------
# Square fetch (placeholder)
# ---------------------------

def fetch_square_orders(start_utc: datetime.datetime, end_utc: datetime.datetime) -> List[Dict[str, Any]]:
    """
    Return a list of normalized orders from Square.
    Each order: same structure as Shopify fetch.
    """
    # For MVP, use Square Orders API (v2). Filter by location + date_time filter.
    # https://developer.squareup.com/reference/square/orders-api/search-orders
    return []

# ---------------------------
# Normalization / persistence
# ---------------------------

def find_product(sku_or_handle: str) -> Product | None:
    """
    Attempt to resolve a Product by SKU first, then by name as a loose fallback.
    You’ll later expand this with a proper mapping UI.
    """
    sku = sku_or_handle.strip()
    product = Product.objects.filter(sku__iexact=sku).first()
    if product:
        return product
    # Fallback: try name match (handle/title)
    return Product.objects.filter(name__iexact=sku).first()

@transaction.atomic
def persist_orders(platform: str, normalized_orders: Iterable[Dict[str, Any]]) -> None:
    """
    Save Order + OrderItems. Idempotent on (order_id, platform).
    """
    for o in normalized_orders:
        order_obj, created = Order.objects.get_or_create(
            order_id=o["order_id"], platform=platform,
            defaults=dict(
                order_date=o["order_date"],
                total_amount=to_decimal(o.get("total_amount", 0)),
                data_raw=_json_safe(o),  # keep raw for debugging
            )
        )
        if not created:
            # Optionally update totals if changed
            order_obj.order_date = o["order_date"]
            order_obj.total_amount = to_decimal(o.get("total_amount", order_obj.total_amount))
            order_obj.save(update_fields=["order_date", "total_amount", "synced_at"])

        # Clear and re-write items (safe for small daily batches)
        order_obj.items.all().delete()

        for item in o.get("items", []):
            sku = item.get("sku_or_handle", "")
            product = find_product(sku)

            if not product:
                # Log this so we can fix mappings later
                print(f"⚠️ Unmapped product SKU: '{sku}' (creating placeholder)")
                product, _ = Product.objects.get_or_create(
                    sku=sku,
                    defaults={"name": f"Unmapped: {sku}"}
            )

            OrderItem.objects.create(
                order=order_obj,
                product=product,
                quantity=int(item.get("quantity", 1)),
                unit_price=to_decimal(item.get("unit_price", 0)),
            )

        # # Clear and re-write items (safe for small daily batches)
        # order_obj.items.all().delete()

        # for item in o.get("items", []):
        #     product = find_product(item.get("sku_or_handle", ""))
        #     OrderItem.objects.create(
        #         order=order_obj,
        #         product=product,
        #         quantity=int(item.get("quantity", 1)),
        #         unit_price=to_decimal(item.get("unit_price", 0)),
        #     )

def aggregate_usage_for_date(target_date: datetime.date) -> Dict[int, Decimal]:
    """
    From OrderItems + RecipeItem, compute total ingredient usage for the date.
    Returns dict {ingredient_id: quantity_used}
    """
    start, end = nyc_day_window(target_date)

    # Fetch order items for the day
    items = (
        OrderItem.objects
        .select_related("order", "product")
        .filter(order__order_date__gte=start, order__order_date__lte=end)
    )

    usage_by_ingredient: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))

    # Build recipe lookup to cut queries
    recipe_map: dict[int, list[RecipeItem]] = defaultdict(list)
    for ri in RecipeItem.objects.select_related("ingredient", "product").all():
        recipe_map[ri.product_id].append(ri)

    for it in items:
        if not it.product_id:
            continue  # unmapped product
        qty_sold = Decimal(it.quantity)
        for ri in recipe_map.get(it.product_id, []):
            usage_by_ingredient[ri.ingredient_id] += (to_decimal(ri.quantity_per_unit) * qty_sold)

    return usage_by_ingredient

@transaction.atomic
def write_usage_logs(target_date: datetime.date, usage: Dict[int, Decimal], source: str):
    """
    Upsert IngredientUsageLog rows for the date and source.
    We store one row per (ingredient, date, source).
    """
    for ingredient_id, qty in usage.items():
        if qty == 0:
            continue
        log, created = IngredientUsageLog.objects.get_or_create(
            ingredient_id=ingredient_id, date=target_date, source=source,
            defaults=dict(quantity_used=qty, calculated_from_orders=True),
        )
        if not created:
            # Update quantity (additive). If you prefer overwrite, replace with assignment.
            log.quantity_used = (to_decimal(log.quantity_used) + qty).quantize(Decimal("0.001"))
            log.calculated_from_orders = True
            log.save(update_fields=["quantity_used", "calculated_from_orders", "note"])

def send_low_stock_email(target_date: datetime.date):
    qs = Ingredient.objects.all().order_by("name")
    lines = []
    include_zero = getattr(settings, "LOW_STOCK_INCLUDE_ZERO", True)

    for ing in qs:
        if ing.reorder_point is None:
            continue
        if (include_zero and ing.current_stock <= ing.reorder_point) or \
           (not include_zero and ing.current_stock > 0 and ing.current_stock <= ing.reorder_point):
            case_info = ""
            if ing.case_size:
                cases = (ing.current_stock / Decimal(ing.case_size)).quantize(Decimal("0.01"))
                case_info = f" (~{cases} cases)"
            lines.append(
                f"- {ing.name}: {ing.current_stock} {ing.unit_type} "
                f"(reorder @ {ing.reorder_point}){case_info}"
            )

    subject = f"[Inventory] Low Stock Report — {target_date.isoformat()}"
    body = (
        f"Daily sync completed for {target_date.isoformat()}.\n\n"
        "Low stock items:\n" +
        ("\n".join(lines) if lines else "None 🎉") +
        "\n\n— Your Django bot"
    )

    if hasattr(settings, "LOW_STOCK_EMAIL_RECIPIENTS") and settings.LOW_STOCK_EMAIL_RECIPIENTS:
        send_mail(
            subject, body,
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
            settings.LOW_STOCK_EMAIL_RECIPIENTS,
            fail_silently=False,
        )

# Put this ABOVE the Command class, at the module level
def _mock_orders_for_date(target_date):
    tz = ZoneInfo(getattr(settings, "SYNC_TIMEZONE", "America/New_York"))
    dt = datetime.datetime.combine(target_date, datetime.time(11, 0), tzinfo=tz)

    shopify = [{
        "order_id": f"sh-{target_date.isoformat()}-001",
        "order_date": dt,
        "total_amount": "45.00",
        "items": [
            {"sku_or_handle": "LATTE-12", "quantity": 6, "unit_price": "4.50"},
            {"sku_or_handle": "BEANS-12", "quantity": 2, "unit_price": "12.00"},
        ],
    }]

    square = [{
        "order_id": f"sq-{target_date.isoformat()}-001",
        "order_date": dt.replace(hour=9),
        "total_amount": "28.50",
        "items": [
            {"sku_or_handle": "LATTE-12", "quantity": 5, "unit_price": "4.50"},
            {"sku_or_handle": "BEANS-12", "quantity": 1, "unit_price": "12.00"},
        ],
    }]

    return shopify, square



# ---------------------------
# Command
# ---------------------------

class Command(BaseCommand):
    help = "Fetch daily orders from Shopify and Square, compute ingredient usage, and email low stock report."

    def add_arguments(self, parser):
        parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD). Defaults to today.")
         parser.add_argument("--start-date", type=str, help="Start date (inclusive) for syncing YYYY-MM-DD")
         parser.add_argument("--end-date", type=str, help="End date (inclusive) for syncing YYYY-MM-DD")
         parser.add_argument("--mock", action="store_true", help="Use mock data instead of API calls")
        parser.add_argument("--dry-run", action="store_true", help="Do everything except write to DB/send email.")
        parser.add_argument("--mock", action="store_true", help="Use mock orders instead of hitting APIs.")


    def handle(self, *args, **options):
        # Target date (cafe day). Default: today, but you may want 'yesterday' if you run at 4 PM.
        # import pytz
        tz = ZoneInfo(getattr(settings, "SYNC_TIMEZONE", "America/New_York"))
        today_local = datetime.datetime.now(tz).date()

        target_date = (
            datetime.date.fromisoformat(options["date"])
            if options.get("date")
            else today_local
        )

        start, end = nyc_day_window(target_date)

        self.stdout.write(self.style.NOTICE(f"Syncing orders for {target_date} ({start} → {end} UTC)"))

        all_orders = []

        # Shopify
        shopify_orders = fetch_shopify_orders(start, end)
        self.stdout.write(f"Shopify orders fetched: {len(shopify_orders)}")
        if not options["dry_run"]:
            persist_orders("shopify", shopify_orders)

        # Square
        square_orders = fetch_square_orders(start, end)
        self.stdout.write(f"Square orders fetched: {len(square_orders)}")
        if not options["dry_run"]:
            persist_orders("square", square_orders)

        # Aggregate usage & write logs
        usage = aggregate_usage_for_date(target_date)
        self.stdout.write(f"Ingredients to log: {len(usage)}")

        if not options["dry_run"]:
            write_usage_logs(target_date, usage, source="shopify")
            write_usage_logs(target_date, usage, source="square")
            send_low_stock_email(target_date)

        self.stdout.write(self.style.SUCCESS("Sync complete."))
        if options.get("mock"):
            self.stdout.write(self.style.WARNING("Running MOCK sync (no external APIs)."))
            shopify_orders, square_orders = _mock_orders_for_date(target_date)

            if not options["dry_run"]:
                persist_orders("shopify", shopify_orders)
                persist_orders("square", square_orders)

            usage = aggregate_usage_for_date(target_date)
            
            if not options["dry_run"]:
                write_usage_logs(target_date, usage, source="shopify")
                write_usage_logs(target_date, usage, source="square")
                send_low_stock_email(target_date)

            self.stdout.write(self.style.SUCCESS("Mock sync complete."))
            return
