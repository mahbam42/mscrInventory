import csv
from decimal import Decimal
from pathlib import Path #Don't need this yet?
from importers._base_Importer import BaseImporter
from importers._handle_extras import handle_extras
from mscrInventory.models import Product, Ingredient, IngredientType, RecipeItem, RecipeModifier, ModifierBehavior

"""
SquareImporter
-----------------
Parses Square daily CSV exports into structured product/modifier data.
Uses BaseImporter for dry-run, logging, and summary reporting.

Outputs a normalized order structure suitable for persist_orders().
"""
class SquareImporter(BaseImporter):
    def process_row(self, row: dict):
        """
        Parse and normalize one Square CSV row into an order-item structure.

        Steps:
        1. Identify the product (Item + Price Point).
        2. Load its base recipe (ingredients + quantities).
        3. Parse modifiers and apply DB-defined RecipeModifier rules.
        4. Return normalized structure for persist_orders().

        Returns:
            dict: {
                "order_id": str,
                "order_date": datetime,
                "total_amount": Decimal,
                "items": [
                    {
                        "sku_or_handle": str,
                        "product_name": str,
                        "quantity": int,
                        "unit_price": Decimal,
                        "recipe_map": {Ingredient: {"qty": Decimal, "type": str}},
                        "modifiers": [ ...parsed modifiers... ],
                    }
                ]
            }
        """
        # --- Identify / normalize product -----------------------------------
        item_name = (row.get("Item") or "").strip()
        price_point = (row.get("Price Point Name") or "").strip()
        product_name = f"{item_name} ({price_point})" if price_point else item_name

        # Try to find product by name or fallback to unmapped stub
        product = (
            Product.objects.filter(name__iexact=product_name).first()
            or Product.objects.filter(name__icontains=item_name).first()
        )
        if not product:
            product, _ = Product.objects.get_or_create(
                name=product_name,
                defaults={"sku": f"UNMAPPED-{item_name[:10].upper()}"}
            )

        # --- Build base recipe map -----------------------------------------
        recipe_map = {}
        for ri in RecipeItem.objects.filter(product=product):
            recipe_map[ri.ingredient] = {
                "qty": Decimal(ri.quantity or 1),
                "type": getattr(getattr(ri.ingredient, "type", None), "name", "MISC"),
            }

        # --- Parse modifiers ------------------------------------------------
        modifiers_raw = row.get("Modifiers Applied", "")
        modifier_names = [m.strip() for m in modifiers_raw.split(",") if m.strip()]
        normalized_modifiers = []

        for mod_name in modifier_names:
            handle_extras(mod_name, recipe_map, normalized_modifiers)

        # --- Summarize item data -------------------------------------------
        quantity = int(float(row.get("Qty", "1").strip() or 1))
        gross_sales = self.parse_money(row.get("Gross Sales", "0"))
        unit_price = gross_sales / quantity if quantity else gross_sales

        normalized_item = {
            "sku_or_handle": product.sku or product.name,
            "product_name": product.name,
            "quantity": quantity,
            "unit_price": unit_price,
            "recipe_map": recipe_map,
            "modifiers": normalized_modifiers,
        }

        # --- Build normalized order ----------------------------------------
        order_id = row.get("Transaction ID") or row.get("Token") or f"NO_ID_{product.id}"
        order_date = self.parse_datetime(
            row.get("Date"), row.get("Time"), row.get("Time Zone")
        )
        total_amount = self.parse_money(row.get("Net Sales", "0"))

        normalized_order = {
            "order_id": order_id,
            "order_date": order_date,
            "total_amount": total_amount,
            "items": [normalized_item],
        }

        # --- Dry-run logging (if enabled) ----------------------------------
        if self.dry_run:
            self.log(f"🧾 {product_name} ×{quantity}", "INFO")
            for m in normalized_modifiers:
                self.log(
                    f"   ↳ {m['behavior']} {m['targets_by_type']} {m['targets_by_name']} ×{m['quantity']}",
                    "DETAIL",
                )
            for ing, meta in recipe_map.items():
                self.log(
                    f"   • {ing.name}: {meta['qty']} ({meta['type']})", "DETAIL",
                )

        return normalized_order
    
    def run_from_file(self, file_path: str):
        """
        Read a Square CSV file, parse each row via process_row(),
        and output normalized orders. If not dry-run, calls persist_orders().
        """
        import csv
        from mscrInventory.management.commands.sync_orders import persist_orders

        normalized_orders = []
        with open(file_path, newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                order = self.process_row(row)
                if order:
                    normalized_orders.append(order)

        if self.dry_run:
            self.log(f"✅ Parsed {len(normalized_orders)} orders (dry-run mode).")
        else:
            persist_orders("square", normalized_orders)
            self.log(f"💾 Imported {len(normalized_orders)} Square orders into DB.")
