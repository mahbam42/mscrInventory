"""
test_square_row.py
------------------
Command to test parsing and import logic for a single row
of a Square CSV file using the same logic as SquareImporter.

Usage:
    python manage.py test_square_row --file squareCSVs/squareCSV_importTest1.csv --row 2 --verbose
"""

import csv
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from importers.square_importer import SquareImporter


class Command(BaseCommand):
    help = "Test parsing of a single row from a Square CSV file using the SquareImporter."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            required=True,
            help="Path to the Square CSV file."
        )
        parser.add_argument(
            "--row",
            type=int,
            required=True,
            help="Row number to test (1-based index)."
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Enable verbose output."
        )

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        row_index = options["row"]
        verbose = options["verbose"]

        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")

        # Read the CSV
        with open(file_path, newline="", encoding="utf-8-sig") as csvfile:
            rows = list(csv.DictReader(csvfile))

        if row_index < 1 or row_index > len(rows):
            raise CommandError(f"Row index {row_index} out of range (1–{len(rows)}).")

        row = rows[row_index - 1]

        # Instantiate the importer in dry-run mode
        importer = SquareImporter(dry_run=True)
        self.stdout.write(f"📄 Testing row {row_index} from {file_path.name}\n")

        # Process the single row with the same logic used in batch imports
        result_buffer = importer._process_row(row, file_path=file_path)

        # Print parsed output
        for line in result_buffer:
            self.stdout.write(line)

        # Optional verbose stats
        if verbose:
            self.stdout.write("\n📊 **Debug Stats**")
            for key, val in importer.stats.items():
                self.stdout.write(f"   {key}: {val}")
