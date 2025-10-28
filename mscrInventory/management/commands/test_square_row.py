import csv
import json
from decimal import Decimal
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.utils.termcolors import colorize

from importers._handle_extras import handle_extras, normalize_modifier
from mscrInventory.models import RecipeItem, Ingredient, RecipeModifier, Product


class Command(BaseCommand):
    help = "Test Square CSV row-to-recipe matching and modifier expansion (safe dry-run)."

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str, required=True, help="Path to Square CSV file.")
        parser.add_argument("--row", type=int, default=1, help="Row number to inspect (1-based index).")
        parser.add_argument("--verbose", action="store_true", help="Show detailed ingredient and modifier expansion.")

    def handle(self, *args, **options):
        file_path = Path(options["file"])
        row_num = options["row"]
        verbose = options["verbose"]

        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")

        self.stdout.write(colorize(f"📄 Testing row {row_num} in {file_path.name}", fg="cyan"))

        # --- Read CSV and extract the desired row
        with open(file_path, newline="", encoding="utf-8-sig") as csvfile:
            reader = list(csv.DictReader(csvfile))
            if row_num < 1 or row_num > len(reader):
                raise CommandError(f"Row {row_num} is out of range. File has {len(reader)} rows.")
            row = reader[row_num - 1]

        # --- Basic row info
        item_name = (row.get("Item Name") or "").strip()
        price_point = (row.get("Price Point Name") or "").strip()
        modifiers_raw = (row.get("Modifiers Applied") or "").strip()
        qty = Decimal(row.get("Qty", "1") or "1")
        gross = Decimal(row.get("Gross Sales", "0").replace("$", "").strip() or "0")

        self.stdout.write(colorize(f"\n🧾 Transaction: {row.get('Transaction ID', '(none)')}", fg="yellow"))
        self.stdout.write(f"Item: {item_name}")
        self.stdout.write(f"Price Point: {price_point or '(none)'}")
        self.stdout.write(f"Modifiers Applied: {modifiers_raw or '(none)'}")
        self.stdout.write(f"Quantity: {qty} | Gross Sales: ${gross:.2f}")

        # --- Match recipe
        display_name = f"{item_name} {price_point}".strip()
        recipe = (
            RecipeItem.objects.filter(ingredient__name__iexact=display_name).first()
            or RecipeItem.objects.filter(ingredient__name__iexact=item_name).first()
        )

        if recipe:
            self.stdout.write(colorize(f"\n✅ Matched base recipe: {RecipeItem.ingredient}", fg="green"))
        else:
            self.stdout.write(colorize("\n⚠️ No recipe match found — will treat as unmapped item.", fg="red"))

        # --- Parse modifiers
        modifiers = [
            m.strip() for m in modifiers_raw.split(",") if m.strip()
        ]
        normalized = [normalize_modifier(m) for m in modifiers]

        # --- Run handle_extras() to simulate modifier expansion
        recipe_map = {i.name: {"qty": Decimal("1.0"), "type": getattr(i.type, "name", "GENERIC")}
                      for i in Ingredient.objects.all()[:5]}  # small dummy map for testing

        """ expanded = []
        for token in normalized:
            result = handle_extras(token, recipe_map, normalized)
            if result:
                expanded.extend(result)
            else:
                expanded.append(token) """
        
        # --- Build recipe_map only if a matching Product (recipe) exists
        expanded = []

        # Try to match by Product name (base item name + price point)
        base_name = f"{item_name} {price_point}".strip()
        product = Product.objects.filter(name__icontains=base_name).first()

        if product:
            print(f"✅ Matched product: {product.name}")
            # Collect all ingredients for this product (its recipe)
            recipe_items = RecipeItem.objects.filter(product=product)
            recipe_map = {
                ri.ingredient.name: {
                    "qty": ri.quantity,
                    "type": getattr(ri.ingredient.type, "name", "GENERIC"),
                }
                for ri in recipe_items
            }
        else:
            print(f"⚠️ No product found matching: {base_name}")
            recipe_map = {}

        # --- Run handle_extras() to simulate modifier expansion (only if recipe exists)
        if recipe_map:
            for token in normalized:
                result = handle_extras(token, recipe_map, normalized)
                if result:
                    expanded.extend(result)
                else:
                    expanded.append(token)
        else:
            expanded = []

        # --- Display results
        self.stdout.write("\n📊 Normalized modifiers:")
        if not normalized:
            self.stdout.write("   (none)")
        else:
            for m in normalized:
                self.stdout.write(f"   - {m}")

        if verbose:
            self.stdout.write("\n🔍 Expansion results:")
            if not expanded:
                self.stdout.write("   (no expansions applied)")
            else:
                for e in expanded:
                    if isinstance(e, dict):
                        pretty = json.dumps(e, indent=2)
                        self.stdout.write(colorize(pretty, fg="blue"))
                    else:
                        self.stdout.write(f"   + {e}")

        # --- Summary
        self.stdout.write("\n📦 Summary:")
        self.stdout.write(f"   Base item: {item_name}")
        self.stdout.write(f"   Price point: {price_point or '(none)'}")
        self.stdout.write(f"🔍 Using recipe_map from: {recipe.name if recipe else 'dummy context'}") #debug line
        self.stdout.write(f"   Modifiers parsed: {len(modifiers)} ({', '.join(modifiers) or 'none'})")
        self.stdout.write(f"   Normalized: {', '.join(normalized) or 'none'}")
        self.stdout.write(f"   Expanded: {len(expanded)} result(s)")

        if not recipe:
            self.stdout.write(colorize("⚠️  This item needs manual recipe mapping.", fg="red"))
        else:
            self.stdout.write(colorize("✅  Parsing completed successfully.", fg="green"))
