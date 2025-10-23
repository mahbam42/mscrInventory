import csv
from pathlib import Path
from importers import BaseImporter
from mscrInventory.models import Product, RecipeModifier


class SquareImporter(BaseImporter):
    """
    Handles parsing Square CSV exports into structured product + modifier usage.
    Supports dry_run mode and logging via BaseImporter.
    """

    def run_from_file(self, filepath):
        """Convenience method to open CSV and pass reader to run()."""
        path = Path(filepath)
        with path.open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            return self.run(reader)

    def process_row(self, row):
        """Handle one row from the Square CSV."""
        item_name = row.get("Item")
        price_point = row.get("Price Point Name", "")
        modifiers_text = row.get("Modifiers Applied", "")

        if not item_name:
            self.counters["skipped"] += 1
            self.log("Skipping row with no item name", "⚠️")
            return

        # Try to find product by name or price point
        product = Product.objects.filter(name__iexact=item_name).first()
        if not product and price_point:
            product = Product.objects.filter(name__icontains=price_point).first()

        if not product:
            self.counters["unmapped"] += 1
            self.log(f"Unmapped product: {item_name}", "❓")
            return

        # Parse modifiers
        modifiers = [
            m.strip().lower() for m in modifiers_text.split(",") if m.strip()
        ]
        matched_modifiers = []
        for mod in modifiers:
            found = RecipeModifier.objects.filter(name__icontains=mod).first()
            if found:
                matched_modifiers.append(found)
            else:
                self.counters["unmapped"] += 1
                self.log(f"Unmapped modifier: {mod}", "❓")

        # For now, just log what we found (no DB writes yet)
        msg = f"{product.name} ({', '.join(m.name for m in matched_modifiers) or 'no modifiers'})"
        self.log(msg, "🧾")
