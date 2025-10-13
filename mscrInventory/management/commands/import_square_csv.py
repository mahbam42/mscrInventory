import csv
import datetime
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
import datetime

from mscrInventory.management.commands.sync_orders import persist_orders

def handle_extras(modifier_name, normalized_modifiers):
    """
    Expand or adjust special modifiers like Dirty Chai, Extra Flavor, Drizzle Cup.
    Returns a list of modifiers to add (could be empty).
    `normalized_modifiers` is the list of parsed modifiers so far for this item.
    """
    extras_to_add = []

    # Normalize input for matching
    mod_lower = modifier_name.strip().lower()

    # 🥄 Extra Flavor → +1 unit to any flavor modifiers already on the item
    if mod_lower == "extra flavor":
        for m in normalized_modifiers:
            if m["type"] == "FLAVOR":
                m["quantity"] = Decimal(m.get("quantity", 1)) + Decimal(1)

    # 🍯 Drizzle Cup → +1 unit to any syrup modifiers already on the item
    elif mod_lower == "drizzle cup":
        for m in normalized_modifiers:
            if m["type"] == "SYRUP":
                m["quantity"] = Decimal(m.get("quantity", 1)) + Decimal(1)

    # ☕ Dirty Chai → expands to "Chai Flavor" (FLAVOR) + "Extra Shot" (EXTRA)
    elif mod_lower == "dirty chai":
        extras_to_add.append({
            "name": "Chai",
            "type": "FLAVOR",
            "quantity": Decimal(1),
        })
        extras_to_add.append({
            "name": "Extra Shot",
            "type": "EXTRA",
            "quantity": Decimal(1),
        })

    # Future specials can go here...

    return extras_to_add

def parse_money(value: str) -> Decimal:
    """Convert strings like '$6.50' or '-$2.66' to Decimal('6.50') / Decimal('-2.66')."""
    if not value:
        return Decimal("0.00")
    value = value.strip().replace("$", "").replace(",", "")
    try:
        return Decimal(value)
    except Exception:
        return Decimal("0.00")


def build_sku_or_handle(row):
    """Construct a stable identifier for mapping based on SKU / Item / Modifiers."""
    sku = row.get("SKU", "").strip()
    item = row.get("Item", "").strip()
    price_point = row.get("Price Point Name", "").strip()
    #modifiers = row.get("Modifiers Applied", "").strip()
    modifiers = [m.strip() for m in row.get("Modifiers Applied", "").split(",") if m.strip()]
    base_flavors = [m for m in modifiers if m in FLAVOR_NAMES]
    base_syrups = [m for m in modifiers if m in SYRUP_NAMES]

    # Detect special flags
    extra_flavor_count = 1 if "Extra Flavor" in modifiers else 0
    drizzle_cup_count = 1 if "Drizzle Cup" in modifiers else 0
    
    if sku:
        return sku

    parts = [item]
    if price_point:
        parts.append(price_point)
    if modifiers:
        parts.append(modifiers)

    return " [".join([parts[0], " | ".join(parts[1:]) + "]"]) if len(parts) > 1 else item


def parse_datetime(date_str: str, time_str: str, tz_str: str):
    """
    Parse Square's date and time with timezone.
    Example: '2025-10-09', '22:40:39', 'Eastern Time (US & Canada)'
    """
    dt_str = f"{date_str} {time_str}"
    dt_naive = datetime.datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    # Square reports are in local tz; for now assume US/Eastern
    local_tz = timezone.get_fixed_timezone(-300)  # UTC-5 baseline; DST may be ignored for simplicity
    dt_local = local_tz.localize(dt_naive) if hasattr(local_tz, "localize") else dt_naive.replace(tzinfo=local_tz)

    return dt_local.astimezone(datetime.timezone.utc)
    #return dt_local.astimezone(timezone.utc)


class Command(BaseCommand):
    help = "Import orders from a Square CSV file (manual export) and store them as Square orders."

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str, required=True, help="Path to Square CSV export file.")

    @transaction.atomic
    def handle(self, *args, **options):
        file_path = Path(options["file"])
        if not file_path.exists():
            raise CommandError(f"File not found: {file_path}")

        self.stdout.write(self.style.NOTICE(f"📥 Importing Square CSV from {file_path}"))

        orders_by_id = {}

        with open(file_path, newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.DictReader(csvfile, delimiter=",")
            for row in reader:
                order_id = row.get("Transaction ID", "").strip()
                if not order_id:
                    continue

                # Parse order date/time
                order_date = parse_datetime(
                    row.get("Date", "").strip(),
                    row.get("Time", "").strip(),
                    row.get("Time Zone", "").strip()
                )

                sku_or_handle = build_sku_or_handle(row)
                quantity = int(float(row.get("Qty", "1").strip() or 1))
                gross_sales = parse_money(row.get("Gross Sales", "0"))
                net_sales = parse_money(row.get("Net Sales", "0"))
                unit_price = (gross_sales / quantity) if quantity else gross_sales

                line_item = {
                    "sku_or_handle": sku_or_handle,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "data_raw": row,
                }

                if order_id not in orders_by_id:
                    orders_by_id[order_id] = {
                        "order_id": order_id,
                        "order_date": order_date,
                        "total_amount": net_sales,
                        "items": [line_item],
                        "raw rows": [],
                    }
                else:
                    orders_by_id[order_id]["items"].append(line_item)
                    orders_by_id[order_id]["total_amount"] += net_sales

                # 👇 THIS is where the modifier parsing & normalization should happen
                modifiers = []
for raw_mod in parse_modifiers_string(row.get("Modifiers Applied", "")):
    extras = handle_extras(raw_mod, modifiers)
    if not extras:  # if it's not a special case, add normally
        modifiers.append(normalize_modifier(raw_mod))
    else:
        modifiers.extend(extras)
#                modifiers_raw = row.get("Modifiers Applied", "")
#                modifiers = [m.strip() for m in modifiers_raw.split(",") if m.strip()]

                # Handle flavor/syrup detection + special flags here
                base_flavors = [m for m in modifiers if m in FLAVOR_NAMES]
                base_syrups = [m for m in modifiers if m in SYRUP_NAMES]
                extra_flavor_count = 1 if "Extra Flavor" in modifiers else 0
                drizzle_cup_count = 1 if "Drizzle Cup" in modifiers else 0

                orders_by_id[transaction_id]["items"].append({
                    "sku_or_handle": row.get("SKU", "").strip(),
                    "name": row.get("Item", "").strip(),
                    "quantity": Decimal(row.get("Qty", "1")),
                    "modifiers": {
                        "flavors": base_flavors,
                        "extra_flavor_count": extra_flavor_count,
                        "syrups": base_syrups,
                        "drizzle_cup_count": drizzle_cup_count,
                    },
                })

        normalized_orders = list(orders_by_id.values())
        self.stdout.write(self.style.NOTICE(f"🧾 Parsed {len(normalized_orders)} Square orders"))

        persist_orders("square", normalized_orders)
        self.stdout.write(self.style.SUCCESS(f"✅ Imported {len(normalized_orders)} Square orders successfully"))

        # Summarize totals
        total_orders = len(normalized_orders)
        total_line_items = sum(len(o["items"]) for o in normalized_orders)
        total_revenue = sum(o["total_amount"] for o in normalized_orders)

        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("📊 Import Summary"))
        self.stdout.write(self.style.HTTP_INFO(f"   Orders:       {total_orders}"))
        self.stdout.write(self.style.HTTP_INFO(f"   Line items:   {total_line_items}"))
        self.stdout.write(self.style.HTTP_INFO(f"   Total revenue: ${total_revenue:.2f}"))
        self.stdout.write("")

        persist_orders("square", normalized_orders)
        self.stdout.write(self.style.SUCCESS(f"✅ Imported {total_orders} Square orders successfully"))

