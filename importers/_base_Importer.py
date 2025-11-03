# mscrInventory/management/commands/_base_importer.py

import csv
import io
from pathlib import Path

from django.utils import timezone


class BaseImporter:
    """
    Abstract importer class providing:
    - dry_run support
    - structured logging (to console or buffer)
    - summary counters for test assertions
    """

    def __init__(self, dry_run=False, log_to_console=True, *, report=False, report_dir=None):
        self.dry_run = dry_run
        self.log_to_console = log_to_console
        self.buffer = io.StringIO()
        self.counters = {
            "added": 0,
            "updated": 0,
            "skipped": 0,
            "unmapped": 0,
            "errors": 0,
        }
        self.start_time = timezone.now()
        self.report_enabled = report
        self.report_dir = Path(report_dir) if report_dir else Path("archive/reports")
        self.report_date = timezone.localdate()

    # ---------------------------------------------------------------------
    # Logging
    # ---------------------------------------------------------------------
    def log(self, message, emoji="💬"):
        timestamp = timezone.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {emoji} {message}"
        self.buffer.write(line + "\n")
        if self.log_to_console:
            print(line)

    # ---------------------------------------------------------------------
    # DB Operation Wrapper
    # ---------------------------------------------------------------------
    def create_or_update(self, model, lookup, defaults=None):
        """
        Helper for consistent CRUD behavior.
        - lookup: dict of filter parameters
        - defaults: dict of values to set/update
        """
        defaults = defaults or {}

        if self.dry_run:
            obj = model.objects.filter(**lookup).first()
            created = obj is None

            if created:
                # Simulate the object that would be created.
                obj = model(**{**lookup, **defaults})
                self.counters["added"] += 1
                self.log(
                    f"[Dry Run] Would create {model.__name__}: {obj}",
                    "🧪",
                )
            elif defaults:
                for key, value in defaults.items():
                    setattr(obj, key, value)
                self.counters["updated"] += 1
                self.log(
                    f"[Dry Run] Would update {model.__name__}: {obj}",
                    "🧪",
                )

            return obj, created

        obj, created = model.objects.get_or_create(**lookup, defaults=defaults)

        if created:
            obj.save()
            self.counters["added"] += 1
            self.log(f"Created {model.__name__}: {obj}", "🆕")
        elif defaults:
            for key, value in defaults.items():
                setattr(obj, key, value)
            obj.save()
            self.counters["updated"] += 1
            self.log(f"Updated {model.__name__}: {obj}", "🔄")

        return obj, created

    # ---------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------
    def summarize(self):
        elapsed = (timezone.now() - self.start_time).total_seconds()
        summary = (
            f"\n📊 Import Summary ({'Dry Run' if self.dry_run else 'Committed'})\n"
            f"Added: {self.counters['added']}\n"
            f"Updated: {self.counters['updated']}\n"
            f"Skipped: {self.counters['skipped']}\n"
            f"Unmapped: {self.counters['unmapped']}\n"
            f"Errors: {self.counters['errors']}\n"
            f"Elapsed: {elapsed:.2f}s\n"
        )
        self.log(summary, "✅")
        if self.report_enabled:
            self._write_report(elapsed)
        return summary

    # ---------------------------------------------------------------------
    # Reporting helpers
    # ---------------------------------------------------------------------
    def _write_report(self, elapsed_seconds: float) -> None:
        """Persist a simple CSV summary when reporting is enabled."""

        try:
            self.report_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.log(f"Unable to create report directory {self.report_dir}: {exc}", "⚠️")
            return

        report_date = getattr(self, "report_date", None) or timezone.localdate()
        filename = f"{report_date.isoformat()}.csv"
        destination = self.report_dir / filename

        headers = ["metric", "value"]
        rows = [
            ("run_mode", "dry-run" if self.dry_run else "live"),
            ("started_at", self.start_time.isoformat()),
            ("elapsed_seconds", f"{elapsed_seconds:.2f}"),
        ]
        rows.extend((key, str(value)) for key, value in self.counters.items())

        with destination.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            for metric, value in rows:
                writer.writerow([metric, value])

        self.log(f"Report written to {destination}", "📝")

    # ---------------------------------------------------------------------
    # Abstract Hooks
    # ---------------------------------------------------------------------
    def process_row(self, row):
        """To be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement process_row()")

    def run(self, csv_reader):
        """Main loop for importers. Pass in a csv.DictReader."""
        self.log(f"Starting {'dry-run' if self.dry_run else 'live'} import...", "🚀")

        for row in csv_reader:
            try:
                self.process_row(row)
            except Exception as e:
                self.counters["errors"] += 1
                self.log(f"Error processing row: {e}", "❌")

        self.summarize()
        return self.buffer.getvalue()
