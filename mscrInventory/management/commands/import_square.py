"""Wrap the SquareImporter for CLI execution with optional usage logging."""

from pathlib import Path
import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from importers.square_importer import SquareImporter  # library module, no Django setup inside
from .sync_orders import write_usage_logs

class Command(BaseCommand):
    """Stream Square CSV rows into the SquareImporter."""
    help = "Import Square CSV via SquareImporter CLI. Supports --dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to Square CSV file.")
        parser.add_argument("--dry-run", action="store_true", help="Simulate only (no DB writes).")
        parser.add_argument(
            "--date",
            type=str,
            help="Business date for logging ingredient usage (YYYY-MM-DD). Defaults to today.",
        )

    def handle(self, *args, **opts):
        file_path = Path(opts["file"])
        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")

        importer = SquareImporter(dry_run=opts["dry_run"])
        self.stdout.write(self.style.NOTICE(
            f"📥 Importing {file_path} {'(dry-run)' if opts['dry_run'] else ''}"
        ))
        try:
            output = importer.run_from_file(file_path)
        except Exception as e:
            raise CommandError(f"Import failed: {e}")

        # Optional: pretty summary from importer
        if output:
            self.stdout.write(output)

        if not opts["dry_run"]:
            usage_totals = importer.get_usage_totals()
            if usage_totals:
                date_str = opts.get("date")
                if date_str:
                    try:
                        target_date = datetime.date.fromisoformat(date_str)
                    except ValueError as exc:
                        raise CommandError(f"Invalid --date value: {date_str}") from exc
                else:
                    target_date = datetime.date.today()
                write_usage_logs(target_date, usage_totals, source="square")
                breakdown = importer.get_usage_breakdown()
                detail_bits = []
                for ingredient_name, per_source in sorted(breakdown.items()):
                    total_qty = sum(per_source.values(), Decimal("0"))
                    detail_bits.append(f"{ingredient_name} × {total_qty}")
                if detail_bits:
                    self.stdout.write(self.style.SUCCESS("📊 Logged Square usage: " + "; ".join(detail_bits)))
                else:
                    self.stdout.write(self.style.SUCCESS(f"📊 Logged Square usage for {len(usage_totals)} ingredient(s)."))
            else:
                self.stdout.write(self.style.WARNING("⚠️ No ingredient usage detected; nothing logged."))

        self.stdout.write(self.style.SUCCESS("✅ Done."))
