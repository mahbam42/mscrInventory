# mscrInventory/management/commands/_base_importer.py

import io
import datetime
from django.utils import timezone


class BaseImporter:
    """
    Abstract importer class providing:
    - dry_run support
    - structured logging (to console or buffer)
    - summary counters for test assertions
    """

    def __init__(self, dry_run=False, log_to_console=True):
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

    # ---------------------------------------------------------------------
    # Logging
    # ---------------------------------------------------------------------
    def log(self, message, emoji="💬"):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
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
        obj, created = model.objects.get_or_create(**lookup, defaults=defaults)

        if not created and defaults:
            for key, value in defaults.items():
                setattr(obj, key, value)
            if not self.dry_run:
                obj.save()
            self.counters["updated"] += 1
            self.log(f"Updated {model.__name__}: {obj}", "🔄")
        else:
            if not self.dry_run:
                obj.save()
            self.counters["added"] += 1
            self.log(f"Created {model.__name__}: {obj}", "🆕")

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
        return summary

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
