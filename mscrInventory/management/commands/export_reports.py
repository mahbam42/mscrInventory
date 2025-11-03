# yourapp/management/commands/export_reports.py
from __future__ import annotations
import csv
import datetime
from pathlib import Path
from decimal import Decimal
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings

from ...utils.reports import (
    aggregate_usage_totals,
    category_profitability,
    cogs_by_day,
    cogs_summary_by_category,
    cogs_summary_by_product,
    cogs_trend_with_variance,
    top_modifiers,
    top_selling_products,
    usage_detail_by_day,
)


class Command(BaseCommand):
    help = "Export CSV reports for a date range: daily COGS summary and ingredient usage detail."

    def add_arguments(self, parser):
        parser.add_argument("--start", required=True, type=str, help="Start date (YYYY-MM-DD)")
        parser.add_argument("--end", required=True, type=str, help="End date (YYYY-MM-DD, inclusive)")
        parser.add_argument("--outdir", type=str, default="archive/reports",
                            help="Output directory (default: ./archive/reports)")
        parser.add_argument("--tz", type=str, default=getattr(settings, "SYNC_TIMEZONE", "America/New_York"),
                            help="Business timezone for day boundaries")

    def handle(self, *args, **opts):
        try:
            start = datetime.date.fromisoformat(opts["start"])
            end = datetime.date.fromisoformat(opts["end"])
        except ValueError:
            raise CommandError("Invalid --start or --end date; expected YYYY-MM-DD")

        if end < start:
            raise CommandError("--end must be >= --start")

        outdir = Path(opts["outdir"])
        outdir.mkdir(parents=True, exist_ok=True)

        tzname = opts["tz"]

        # 1) Daily COGS summary
        cogs_rows = cogs_by_day(start, end, tzname=tzname)
        cogs_path = outdir / f"cogs_by_day_{start}_{end}.csv"
        with cogs_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "cogs_total"])
            for r in cogs_rows:
                writer.writerow([r["date"], f"{r['cogs_total']:.2f}"])

        # 2) Ingredient usage detail (with unit cost snapshot as-of-day)
        usage_rows = usage_detail_by_day(start, end)
        usage_path = outdir / f"usage_detail_{start}_{end}.csv"
        with usage_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["date", "ingredient", "qty_used", "unit_cost_as_of_day", "cogs"])
            for r in usage_rows:
                writer.writerow([
                    r["date"],
                    r["ingredient"],
                    f"{r['qty_used']:.3f}",
                    f"{r['unit_cost']:.4f}",
                    f"{r['cogs']:.2f}",
                ])

        # 3) Aggregated reporting summary
        product_rows = cogs_summary_by_product(start, end)
        category_rows = cogs_summary_by_category(start, end)
        profitability = category_profitability(start, end)
        trend_rows = cogs_trend_with_variance(start, end, tzname=tzname)
        top_products = top_selling_products(start, end)
        modifier_rows = top_modifiers(start, end)
        usage_totals = aggregate_usage_totals(start, end)

        label = start.isoformat() if start == end else f"{start}_{end}"
        summary_path = outdir / f"{label}.csv"
        with summary_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Reporting Window", start.isoformat(), end.isoformat()])
            writer.writerow([])
            writer.writerow(["Overall Revenue", f"{profitability['overall_revenue']:.2f}"])
            writer.writerow(["Overall COGS", f"{profitability['overall_cogs']:.2f}"])
            writer.writerow(["Overall Profit", f"{profitability['overall_profit']:.2f}"])
            writer.writerow([
                "Overall Margin %",
                profitability["overall_margin_pct"] if profitability["overall_margin_pct"] is not None else "",
            ])

            writer.writerow([])
            writer.writerow(["Per Product Summary"])
            writer.writerow(["product", "sku", "quantity", "revenue", "cogs", "profit", "margin_pct"])
            for row in product_rows:
                writer.writerow([
                    row["product_name"],
                    row["sku"],
                    f"{row['quantity']:.0f}",
                    f"{row['revenue']:.2f}",
                    f"{row['cogs']:.2f}",
                    f"{row['profit']:.2f}",
                    row["margin_pct"] if row["margin_pct"] is not None else "",
                ])

            writer.writerow([])
            writer.writerow(["Per Category Summary"])
            writer.writerow(["category", "quantity", "revenue", "cogs", "profit", "margin_pct"])
            for row in category_rows:
                writer.writerow([
                    row["category"],
                    f"{row['quantity']:.0f}",
                    f"{row['revenue']:.2f}",
                    f"{row['cogs']:.2f}",
                    f"{row['profit']:.2f}",
                    row["margin_pct"] if row["margin_pct"] is not None else "",
                ])

            writer.writerow([])
            writer.writerow(["Top Selling Products"])
            writer.writerow(["product", "descriptors", "modifiers", "quantity", "gross_sales"])
            for row in top_products:
                writer.writerow([
                    row["product_name"],
                    ", ".join(row["adjectives"]),
                    ", ".join(row["modifiers"]),
                    f"{row['quantity']:.0f}",
                    f"{row['gross_sales']:.2f}",
                ])

            writer.writerow([])
            writer.writerow(["Top Modifiers"])
            writer.writerow(["modifier", "quantity", "gross_sales"])
            for row in modifier_rows:
                writer.writerow([
                    row["modifier"],
                    f"{row['quantity']:.0f}",
                    f"{row['gross_sales']:.2f}",
                ])

            writer.writerow([])
            writer.writerow(["COGS Trend"])
            writer.writerow(["date", "cogs", "variance", "variance_pct"])
            for row in trend_rows:
                writer.writerow([
                    row["date"],
                    f"{row['cogs_total']:.2f}",
                    f"{row['variance']:.2f}" if row["variance"] is not None else "",
                    row["variance_pct"] if row["variance_pct"] is not None else "",
                ])

            writer.writerow([])
            writer.writerow(["Ingredient Usage Totals"])
            writer.writerow(["ingredient", "quantity"])
            for name, qty in sorted(usage_totals.items()):
                writer.writerow([name, f"{qty:.3f}"])

        self.stdout.write(self.style.SUCCESS(f"Wrote: {cogs_path}"))
        self.stdout.write(self.style.SUCCESS(f"Wrote: {usage_path}"))
        self.stdout.write(self.style.SUCCESS(f"Wrote: {summary_path}"))
