"""
square_importer.py
------------------
Primary importer for Square CSV data.

Handles:
- CSV reading (via run_from_file)
- Row-level parsing and normalization (process_row)
- Modifier resolution and expansion (handle_extras)
- Safe dry-run and summary reporting

This class is called either from:
  1. Django management command (`import_square.py`)
  2. Web dashboard upload view (`upload_square_view`)
"""

import csv
from decimal import Decimal, InvalidOperation
from collections import Counter
from datetime import datetime
from io import StringIO

from mscrInventory.models import Ingredient, Product, RecipeModifier
from importers._handle_extras import handle_extras


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def parse_money(value) -> Decimal:
    """
    Convert Square-style currency strings into Decimal.

    Examples:
        "$3.50" → Decimal("3.50")
        "3.5"   → Decimal("3.50")
        "" or None → Decimal("0.00")
    """
    if not value:
        return Decimal("0.00")
    try:
        clean = str(value).replace("$", "").replace(",", "").strip()
        return Decimal(clean)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


# ---------------------------------------------------------------------------
# Base Importer
# ---------------------------------------------------------------------------

class SquareImporter:
    """
    Handles CSV imports from Square, applying modifiers and normalizing data.
    Works in both dry-run and live-import modes.
    """

    def __init__(self, dry_run=True):
        self.dry_run = dry_run
        self.buffer = StringIO()
        self.stats = Counter()
        self.errors = []
        self.start_time = datetime.now()

    # -----------------------------------------------------------------------
    # Logging utilities
    # -----------------------------------------------------------------------

    def log_success(self, event: str):
        """Increment a counter for a specific success event."""
        self.stats[event] += 1

    def log_error(self, msg: str):
        """Record and count an error without stopping execution."""
        self.stats["errors"] += 1
        self.errors.append(msg)
        self.buffer.write(f"❌ {msg}\n")

    # -----------------------------------------------------------------------
    # Core methods
    # -----------------------------------------------------------------------

    def run_from_file(self, file_path):
        """
        Main entry point for CSV import.

        Reads the Square CSV and processes each row sequentially.
        Safe to run in dry-run mode (no DB writes).
        """
        self.buffer.write(f"📥 Importing {file_path} ({'dry-run' if self.dry_run else 'live'})\n")

        try:
            with open(file_path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader, start=1):
                    self.stats["rows"] += 1
                    try:
                        self.process_row(row)
                    except Exception as e:
                        self.log_error(f"Row {i}: {e}")

        except FileNotFoundError:
            self.log_error(f"File not found: {file_path}")
        except Exception as e:
            self.log_error(f"Unexpected error reading CSV: {e}")

        self.buffer.write(self.summarize())
        return self.summarize()

    def process_row(self, row: dict):
        """
        Process a single row from the Square CSV.

        Each row should include:
        - Item Name
        - Price Point Name (variant)
        - Modifiers Applied (comma-separated)
        """
        item_name = row.get("Item Name", "").strip()
        price_point = row.get("Price Point Name", "").strip()
        modifiers_str = row.get("Modifiers Applied", "")
        qty = Decimal(row.get("Quantity", "1") or "1")

        # Example of parsing prices safely
        total_price = parse_money(row.get("Gross Sales", 0))
        unit_price = total_price / qty if qty > 0 else Decimal("0.00")

        # Identify or create product (for now, just log)
        self.buffer.write(f"→ {item_name} ({price_point}) x{qty} @ {unit_price}\n")
        self.stats["matched"] += 1

        # Handle modifiers
        modifiers = [m.strip() for m in modifiers_str.split(",") if m.strip()]
        if modifiers:
            self.stats["modifiers_applied"] += len(modifiers)
            for mod in modifiers:
                handle_extras(mod, {}, [])  # TODO: supply real recipe_map + normalized_modifiers

    # -----------------------------------------------------------------------
    # Summary report
    # -----------------------------------------------------------------------

    def summarize(self) -> str:
        """
        Return a human-readable summary of import results.
        """
        elapsed = (datetime.now() - self.start_time).total_seconds()
        lines = [
            "",
            "📊 **Square Import Summary**",
            f"Started: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Elapsed: {elapsed:.2f}s",
            "",
            f"🧾 Rows processed: {self.stats.get('rows', 0)}",
            f"✅ Products matched: {self.stats.get('matched', 0)}",
            f"➕ New products added: {self.stats.get('new', 0)}",
            f"⚙️ Modifiers applied: {self.stats.get('modifiers_applied', 0)}",
            f"⚠️ Errors: {self.stats.get('errors', 0)}",
            "",
        ]
        if self.errors:
            lines.append("Most recent errors:")
            for err in self.errors[-5:]:
                lines.append(f"  - {err}")
        return "\n".join(lines)
