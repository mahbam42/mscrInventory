"""Management command to synchronise Shopify orders and ingredient usage."""

from __future__ import annotations
import datetime
from decimal import Decimal
from typing import Any, Dict
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.mail import send_mail

from importers.shopify_importer import ShopifyImporter, _format_decimal
from ...models import Ingredient, IngredientUsageLog


def nyc_day_window(target_date: datetime.date) -> tuple[datetime.datetime, datetime.datetime]:
    """Return the UTC start/end datetimes for the cafe day in New York."""

    tz = ZoneInfo(getattr(settings, "SYNC_TIMEZONE", "America/New_York"))
    start_local = datetime.datetime.combine(target_date, datetime.time.min, tzinfo=tz)
    end_local = datetime.datetime.combine(target_date, datetime.time.max, tzinfo=tz)
    return start_local.astimezone(datetime.timezone.utc), end_local.astimezone(datetime.timezone.utc)


def write_usage_logs(target_date: datetime.date, usage: Dict[int, Decimal], *, source: str) -> None:
    """Upsert IngredientUsageLog rows using the provided totals."""

    for ingredient_id, qty in usage.items():
        quantity = Decimal(qty)
        if quantity <= 0:
            continue
        quantity = quantity.quantize(Decimal("0.001"))
        log, created = IngredientUsageLog.objects.get_or_create(
            ingredient_id=ingredient_id,
            date=target_date,
            source=source,
            defaults=dict(quantity_used=quantity, calculated_from_orders=True),
        )
        if not created:
            log.quantity_used = quantity
            log.calculated_from_orders = True
            log.save(update_fields=["quantity_used", "calculated_from_orders", "note"])


def send_low_stock_email(target_date: datetime.date) -> None:
    qs = Ingredient.objects.all().order_by("name")
    lines = []
    include_zero = getattr(settings, "LOW_STOCK_INCLUDE_ZERO", True)

    for ingredient in qs:
        if ingredient.reorder_point is None:
            continue
        on_hand = Decimal(ingredient.current_stock or 0)
        reorder_point = Decimal(ingredient.reorder_point or 0)
        if include_zero and on_hand <= reorder_point:
            should_include = True
        elif not include_zero and 0 < on_hand <= reorder_point:
            should_include = True
        else:
            should_include = False
        if not should_include:
            continue
        case_info = ""
        if ingredient.case_size:
            cases = (on_hand / Decimal(ingredient.case_size)).quantize(Decimal("0.01"))
            case_info = f" (~{cases} cases)"
        lines.append(
            f"- {ingredient.name}: {on_hand} {ingredient.unit_type} (reorder @ {reorder_point}){case_info}"
        )

    subject = f"[Inventory] Low Stock Report — {target_date.isoformat()}"
    body = (
        f"Daily sync completed for {target_date.isoformat()}.\n\n"
        "Low stock items:\n" +
        ("\n".join(lines) if lines else "None 🎉") +
        "\n\n— Your Django bot"
    )

    recipients = getattr(settings, "LOW_STOCK_EMAIL_RECIPIENTS", None)
    if recipients:
        send_mail(
            subject,
            body,
            getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
            recipients,
            fail_silently=False,
        )


def _mock_orders_for_date(target_date: datetime.date) -> list[Dict[str, Any]]:
    """Return deterministic mock Shopify orders for tests/demos."""

    tz = ZoneInfo(getattr(settings, "SYNC_TIMEZONE", "America/New_York"))
    order_time = datetime.datetime.combine(target_date, datetime.time(11, 0), tzinfo=tz)

    return [
        {
            "id": f"sh-{target_date.isoformat()}-001",
            "created_at": order_time.isoformat(),
            "total_price": "42.00",
            "line_items": [
                {
                    "sku": "COFFEE-RET-BAG",
                    "title": "Mike's Perfecto Retail Bag",
                    "variant_title": "11 oz / Whole Bean",
                    "quantity": 2,
                    "price": "18.00",
                },
                {
                    "sku": "TUMBLER-01",
                    "title": "Tumbler",
                    "quantity": 1,
                    "price": "6.00",
                },
            ],
        }
    ]


class Command(BaseCommand):
    help = "Fetch daily orders from Shopify, compute ingredient usage, and email the low stock report."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--date", type=str, help="Target date (YYYY-MM-DD). Defaults to today.")
        parser.add_argument("--start-date", type=str, help="Start date (inclusive) for syncing YYYY-MM-DD")
        parser.add_argument("--end-date", type=str, help="End date (inclusive) for syncing YYYY-MM-DD")
        parser.add_argument("--dry-run", action="store_true", help="Do everything except write to DB/send email.")
        parser.add_argument("--mock", action="store_true", help="Use mock orders instead of hitting Shopify APIs.")

    def handle(self, *args, **options):
        dry_run: bool = options.get("dry_run", False)
        mock: bool = options.get("mock", False)
        date_str: str | None = options.get("date")
        start_str: str | None = options.get("start_date")
        end_str: str | None = options.get("end_date")
        verbosity: int = int(options.get("verbosity", 1))

        if date_str:
            target_date = datetime.date.fromisoformat(date_str)
            self._sync_for_date(target_date, dry_run=dry_run, mock=mock, verbosity=verbosity)
            return

        if start_str and end_str:
            start_date = datetime.date.fromisoformat(start_str)
            end_date = datetime.date.fromisoformat(end_str)
            if start_date > end_date:
                raise CommandError("❌ --start-date must be before --end-date")

            current = start_date
            while current <= end_date:
                self.stdout.write(self.style.NOTICE(f"📅 Syncing {current}"))
                self._sync_for_date(current, dry_run=dry_run, mock=mock, verbosity=verbosity)
                current += datetime.timedelta(days=1)
            return

        raise CommandError("❌ Must provide --date OR --start-date and --end-date")

    def _sync_for_date(
        self,
        target_date: datetime.date,
        *,
        dry_run: bool,
        mock: bool,
        verbosity: int,
    ) -> Dict[int, Decimal]:
        start_utc, end_utc = nyc_day_window(target_date)
        log_to_console = verbosity > 1
        importer = ShopifyImporter(dry_run=dry_run, log_to_console=log_to_console)

        if mock:
            orders = _mock_orders_for_date(target_date)
            self.stdout.write(self.style.WARNING("Running mock Shopify sync (no external API calls)."))
        else:
            orders = None

        usage = importer.import_window(start_utc, end_utc, orders=orders)
        usage_breakdown = importer.get_usage_breakdown()

        orders_added = importer.counters.get("added", 0)
        orders_updated = importer.counters.get("updated", 0)
        matched_items = importer.counters.get("matched", 0)
        unmapped_items = importer.counters.get("unmapped", 0)

        summary = (
            f"✨ Shopify sync complete for {target_date}: "
            f"{orders_added} added, {orders_updated} updated, "
            f"{matched_items} items matched, {unmapped_items} unmapped"
        )
        self.stdout.write(self.style.SUCCESS(summary))

        if usage_breakdown:
            self.stdout.write("Ingredient usage detail:")
            for ingredient_name, per_source in sorted(usage_breakdown.items()):
                total_qty = sum(per_source.values(), Decimal("0"))
                self.stdout.write(f"  - {ingredient_name}: {_format_decimal(total_qty)}")
                for source, qty in sorted(per_source.items()):
                    self.stdout.write(f"      • {source}: {_format_decimal(qty)}")

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run enabled; no database writes performed."))
            return usage

        if usage:
            write_usage_logs(target_date, usage, source=ShopifyImporter.platform)
            send_low_stock_email(target_date)
            self.stdout.write(self.style.SUCCESS(
                f"📊 Logged usage for {len(usage)} ingredient(s) from Shopify orders."
            ))
        else:
            self.stdout.write(self.style.WARNING("No ingredient usage detected for this date."))

        return usage
