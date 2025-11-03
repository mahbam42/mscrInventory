"""Management command to purge import-related data with a safe snapshot."""

from __future__ import annotations

import json
from pathlib import Path

from django.core.management import BaseCommand, call_command
from django.db import transaction
from django.utils import timezone

from mscrInventory.models import (
    IngredientUsageLog,
    Order,
    OrderItem,
    ImportLog,
    SquareUnmappedItem,
)


ARCHIVE_DIR = Path("archive")
SNAPSHOT_BASENAME = "purgeImports"
SNAPSHOT_SUFFIX = ".json"


class Command(BaseCommand):
    help = (
        "Create a JSON snapshot of import data and purge tables so the same "
        "test data can be recycled between runs."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--include-logs",
            action="store_true",
            help="Also purge ImportLog and SquareUnmappedItem records.",
        )
        parser.add_argument(
            "--no-snapshot",
            action="store_true",
            help="Skip creating the JSON snapshot (NOT recommended).",
        )

    def handle(self, *args, **options):
        include_logs = options["include_logs"]
        create_snapshot = not options["no_snapshot"]

        if create_snapshot:
            snapshot_path = self._create_snapshot(include_logs=include_logs)
            self.stdout.write(
                self.style.SUCCESS(
                    f"📦 Snapshot written to {snapshot_path}. "
                    "Restore with: python manage.py loaddata "
                    f"{snapshot_path}"
                )
            )
        else:
            snapshot_path = None
            self.stdout.write(self.style.WARNING("⚠️ Skipping snapshot creation."))

        deleted = self._purge(include_logs=include_logs)

        summary = ", ".join(f"{model}: {count}" for model, count in deleted.items())
        self.stdout.write(self.style.SUCCESS(f"🧹 Purged records — {summary or 'nothing removed.'}"))

        if snapshot_path:
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    "✅ Ready to import fresh data. Use the snapshot command above to restore when needed."
                )
            )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _next_snapshot_path(self) -> Path:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        existing = sorted(ARCHIVE_DIR.glob(f"{SNAPSHOT_BASENAME}*{SNAPSHOT_SUFFIX}"))

        next_index = 1
        if existing:
            latest = existing[-1].stem  # e.g., purgeImports12
            suffix = latest.replace(SNAPSHOT_BASENAME, "")
            try:
                next_index = int(suffix) + 1
            except ValueError:
                next_index = 1

        timestamp = timezone.now().strftime("%Y%m%d-%H%M%S")
        filename = f"{SNAPSHOT_BASENAME}{next_index:03d}-{timestamp}{SNAPSHOT_SUFFIX}"
        return ARCHIVE_DIR / filename

    def _create_snapshot(self, *, include_logs: bool) -> Path:
        snapshot_path = self._next_snapshot_path()
        models = [
            "mscrInventory.IngredientUsageLog",
            "mscrInventory.OrderItem",
            "mscrInventory.Order",
        ]
        if include_logs:
            models += [
                "mscrInventory.ImportLog",
                "mscrInventory.SquareUnmappedItem",
            ]

        with snapshot_path.open("w", encoding="utf-8") as handle:
            call_command(
                "dumpdata",
                *models,
                indent=2,
                stdout=handle,
            )

        # Minimal validation that file is valid JSON
        with snapshot_path.open("r", encoding="utf-8") as handle:
            json.load(handle)

        return snapshot_path

    def _purge(self, *, include_logs: bool) -> dict[str, int]:
        deleted_counts: dict[str, int] = {}

        with transaction.atomic():
            deleted_counts["OrderItem"] = OrderItem.objects.all().delete()[0]
            deleted_counts["Order"] = Order.objects.all().delete()[0]
            deleted_counts["IngredientUsageLog"] = IngredientUsageLog.objects.all().delete()[0]

            if include_logs:
                deleted_counts["ImportLog"] = ImportLog.objects.all().delete()[0]
                deleted_counts["SquareUnmappedItem"] = SquareUnmappedItem.objects.all().delete()[0]

        return deleted_counts
