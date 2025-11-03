"""Management command to feed ShopifyImporter with CSV data (no API call)."""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, date, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from importers.shopify_importer import ShopifyImporter


class Command(BaseCommand):
    help = (
        "Load a CSV that mimics Shopify order exports and run ShopifyImporter "
        "against it without hitting the API."
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=Path, help="Path to the CSV file.")
        parser.add_argument(
            "--date",
            type=str,
            help="Cafe date (YYYY-MM-DD) for the import window; defaults to today's date.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run importer in dry-run mode (no DB writes).",
        )
        parser.add_argument(
            "--verbosity",
            type=int,
            choices=[0, 1, 2],
            default=1,
            help="Logging verbosity for importer output.",
        )

    def handle(self, *args, **options):
        csv_path: Path = options["csv_path"]
        if not csv_path.exists():
            raise CommandError(f"CSV file not found: {csv_path}")

        target_date = (
            datetime.fromisoformat(options["date"]).date()
            if options.get("date")
            else timezone.localdate()
        )
        orders = self._parse_orders(csv_path, default_date=target_date)

        if not orders:
            self.stdout.write(self.style.WARNING("No order rows found in CSV; nothing to import."))
            return

        start_utc, end_utc = self._window_for_orders(orders, target_date)

        importer = ShopifyImporter(
            dry_run=options["dry_run"],
            log_to_console=bool(options["verbosity"] and options["verbosity"] > 1),
        )

        self.stdout.write(
            self.style.NOTICE(
                f"📄 Importing {len(orders)} mocked Shopify order(s) "
                f"from {csv_path.name} ({start_utc.isoformat()} → {end_utc.isoformat()})."
            )
        )

        importer.import_window(start_utc, end_utc, orders=orders)
        importer.summarize()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _parse_orders(self, csv_path: Path, default_date: date) -> list[dict]:
        """
        Expected columns (case-insensitive):
        - order_id (optional; auto-generated when missing)
        - created_at (ISO or YYYY-MM-DD; defaults to `default_date` @ 10:00)
        - sku, title, variant_title (strings)
        - quantity (int)
        - price (per-unit decimal)
        """
        with csv_path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise CommandError("CSV file is missing headers.")

            orders_map: dict[str, dict] = {}
            line_index = 0
            for row in reader:
                line_index += 1
                order_id = (row.get("order_id") or row.get("Order ID") or "").strip()
                if not order_id:
                    order_id = f"csv-{line_index:04d}"

                created_at_raw = (
                    row.get("created_at") or row.get("Created At") or row.get("created")
                )
                created_at = self._parse_datetime(created_at_raw, default_date)

                order = orders_map.setdefault(
                    order_id,
                    {
                        "id": order_id,
                        "created_at": created_at.isoformat(),
                        "name": order_id,
                        "total_price": Decimal("0"),
                        "line_items": [],
                    },
                )

                qty = self._parse_int(row.get("quantity") or row.get("Qty") or "1")
                price = Decimal(str(row.get("price") or row.get("Price") or "0") or "0")
                total_line = price * qty

                order["total_price"] = Decimal(order["total_price"]) + total_line

                order["line_items"].append(
                    {
                        "sku": (row.get("sku") or row.get("SKU") or "").strip(),
                        "title": (row.get("title") or row.get("Title") or "").strip(),
                        "variant_title": (row.get("variant_title") or row.get("Variant Title") or "").strip(),
                        "quantity": qty,
                        "price": str(price),
                    }
                )

        return list(orders_map.values())

    def _window_for_orders(self, orders: list[dict], default_date: date) -> tuple[datetime, datetime]:
        created_list = []
        for order in orders:
            created_list.append(datetime.fromisoformat(order["created_at"]))

        if not created_list:
            start_local = datetime.combine(default_date, time.min, tzinfo=timezone.get_current_timezone())
            end_local = datetime.combine(default_date, time.max, tzinfo=timezone.get_current_timezone())
        else:
            start_local = min(created_list)
            end_local = max(created_list) + timedelta(seconds=1)

        return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)

    @staticmethod
    def _parse_int(value: str | None) -> int:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _parse_datetime(value: str | None, fallback_date: date) -> datetime:
        tz = timezone.get_current_timezone()
        if not value:
            return datetime.combine(fallback_date, time(10, 0), tz)
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = tz.localize(dt)
            return dt
        except Exception:
            return datetime.combine(fallback_date, time(10, 0), tz)

