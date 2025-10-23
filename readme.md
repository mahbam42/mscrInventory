# 🧾 MSCR Inventory App

A lightweight, Django + HTMX-based inventory and recipe management system for Mike Shea Coffee Roasters.
It’s designed for small production environments — blending real-time usability for staff with enough structure for analytics, costing, and reporting.

## 🚀 Features

### Inventory Management

- 📦 Bulk Add Modal – Add or adjust multiple stock entries at once.
- 📥 CSV Import / Export – Snapshot inventory for offline edits, then re-import changes.
- 🧾 StockEntry Records – Every transaction (restock, spoilage, adjustment) creates a tracked entry.
- 💰 Average Cost Tracking – Updates ingredient cost based on weighted average from new entries.

### Recipe Management

- 🧮 COGS Preview – Calculate recipe cost dynamically from ingredient data.
- 📤 CSV Export – Export recipes with their ingredient breakdowns for external editing.
- 📥 CSV Import (Preview + Confirm) – Two-step modal for safe data injection with dry-run validation.
- ⚠️ Invalid Row Handling – Clearly separates valid and invalid data during import.
- 💾 Dry-Run Mode – Validate data without writing to the database.
- 🪵 Logging – All imports logged to archive/logs/import_recipes.log.

### User Interface

- ⚡ HTMX-Powered Dashboards – Responsive modals, instant updates, no page reloads.
- 🔍 Search and Category Filters – Live recipe and inventory filtering.
- 🧱 Bootstrap 5 Layouts – Clean, mobile-friendly UI without JS frameworks.

## Installation

~~~
  1.  git clone https://github.com/mahbam42/mscrInventory.git
  2.  cd mscrInventory
  3.  python3 -m venv venv
  4.  source venv/bin/activate
  5.  pip install -r requirements.txt
  6.  python manage.py migrate
  7.  python manage.py runserver
~~~
  8. Then open: http://127.0.0.1:8000/inventory/

## 🧪 Testing

All tests are written for pytest + Django.

~~~
pytest -v
~~~

Example tests

- test_bulk_add_stock_creates_entries
- test_import_inventory_csv_updates_data
- test_export_recipes_csv_contains_expected_columns
- test_import_recipes_csv_dry_run_does_not_write

### 🧰 Management Commands
Command	Description: 
- python manage.py import_square_csv
 - Parse daily Square sales exports

- python manage.py import_recipes_from_csv
 -  Bulk create or update recipes

- python manage.py import_chemistry
 - Import or sync from stored CSV chemistry data

- python manage.py clean_empty_recipeitems
 - Remove orphaned or duplicate recipe items

All commands support a --dry-run flag for safe testing.

### 🪵 Logs & Archives

- ~~~ archive/logs/ ~~~
 - Import logs and dry-run records.

- ~~~ archive/recipes/ ~~~
 - Archived recipe CSVs.

- ~~~ archive/squareCSVs/ ~~~
 - Imported Square data snapshots.

- ~~~ archive/data/seed.json ~~~
 - Optional fixture for seeding dev DBs.

### 🧱 Phase Overview

Phase 1	Foundation: Inventory + models	✅ Complete
Phase 2	COGS, Import/Export, UI consistency	✅ Complete
Phase 3	Parser refactor, Unmapped items, Extras logic	🧩 In progress
Phase 4	Reporting + COGS history + cost summaries	🧭 Planned
Phase 5	Integration polish (Shopify / Square sync)	⏳ Future
🧑‍💻 Development Notes

Designed for clarity and maintainability, not raw performance.

Avoids heavy dependencies: just Django, HTMX, and Bootstrap.

CSV-based import/export doubles as the app’s internal API.

All forms and modals use hx-target and HX-Trigger for live updates.