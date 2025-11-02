# mscrInventory/management/commands/import_square.py
"""
Management Command: import_square
---------------------------------
Usage:
    python manage.py import_square --file path/to/file.csv [--dry-run]

This wraps SquareImporter for CLI execution.
Safe for production and web dashboard integration.
"""

from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from importers.square_importer import SquareImporter  # library module, no Django setup inside

class Command(BaseCommand):
    help = "Import Square CSV via SquareImporter CLI. Supports --dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Path to Square CSV file.")
        parser.add_argument("--dry-run", action="store_true", help="Simulate only (no DB writes).")

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
        self.stdout.write(self.style.SUCCESS("✅ Done."))
