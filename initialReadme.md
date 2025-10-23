# Product Mapping

- The app will fetch product lists dynamically from both Square and Shopify (via their APIs).
- Admins can then view a “Product Mapping” page to link items between systems (Shopify SKU ↔ Square Item ID).
- Any unmapped products will be clearly listed as “Unmapped” to prompt configuration.
- Optional: auto-match by name or SKU when possible, with manual override.


## Inventory Management
- Add case_size and unit_per_case fields to each inventory item:
e.g., “Cups” → 500 units per case
- This allows tracking by usable units while still representing case-level stock.
- Stock level displays in both cases and units for clarity.
- Existing fields retained: current_stock, reorder_point, unit_type, and optional lead_time.


## Automatic Ingredient Depletion
- Ingredient usage will feed into the daily report and dashboard.
- A new “Usage Dashboard” will visualize:
- Ingredient consumption by date range
- Remaining stock levels
- Alerts for low or negative inventory


## Reporting
- Reports can be filtered by date range (daily, weekly, custom).
- Export options: CSV and PDF (PDF later if needed).
- Summary report emailed daily at 4:15 PM EST after sync.


## COGS (Cost of Goods Sold)
- Add fields:
  - Ingredient.cost_per_unit
  - Auto-calculate COGS for each product = Σ(ingredient_qty × cost_per_unit)
- Later, aggregate by day/week to report total COGS vs. revenue.


## Manual Sync
- Include a button on the admin dashboard to trigger a full or partial data sync for a chosen date range.

# Scoped Feature Roadmap
Here’s a practical development roadmap, keeping in mind you’ll host this locally at first:

##  Phase 1 — Core MVP (Proof of Concept)
Goal: Fetch daily orders, calculate ingredient usage, and send summary email.
Features:
- Django project setup (DRF, Celery, Redis)
- Models: Product, Ingredient, Recipe, InventoryItem, Order, IngredientUsageLog


### Integrations:
- Shopify API: fetch daily orders
- Square API: fetch daily orders
- Daily scheduled task at 4 PM EST
- Recipe-based inventory depletion
- Reorder threshold tracking (reorder_point)
- Daily email report (orders summary + low-stock alerts)

### Phase 2 — Dashboards & Manual Tools
Goal: Add visibility and control from the web UI.
Features:
- Django admin views or lightweight front-end dashboard:
- Inventory dashboard (current stock, reorder flags)
- Usage dashboard (daily ingredient depletion)
- Reporting dashboard (filter by date range)
- Manual stock adjustments (restocks, waste)
- Manual sync trigger (date range selectable)
- Case size support for inventory
- Product mapping interface (dynamic fetch + linking)

### Phase 3 — Data Enhancements & Exports
Goal: Make data more valuable and portable.
Features:
- Ingredient cost tracking (cost_per_unit)
- COGS calculation per product and per period
- CSV export for reports (PDF optional later)
- Add lead_time to ingredients and highlight long-lead items nearing reorder point

### Phase 4 — Polish & Automation
Goal: Improve usability, automation, and reporting accuracy.
Features:
- Basic role-based permissions
- Sync logs and error notifications
- Auto-matching of products by SKU/name during sync
- longitudinal analytics (weekly/monthly charts)
- Optional: PDF export and email attachments

### Optional Future Phase 
- Real-time webhook sync
- Multi-location inventory tracking
- Supplier management (auto-generate reorder lists)
- Forecasting (usage trends → reorder projections)

## In progress Wishlist
- Export Products, Recipes
- fix dashboard to use base.html
- make base.html navigation dynamic
- dirty chai refactor to extra modifier (chai flavorshot + extra shot)
- refreshers modifiers
- bagel modifiers
- croissant/biscuit modifiers
- hot coffee modifiers
- pour over modifiers
- Bagged Coffee (retail bag) and association with Shopify Listings

### Products Dashboard
- Show Name, SKU, Categories, Type (is_drink, is_food, is_coffee), and temp.
- Edit button wired to modal
- import CSV at the top (and dedup-ing logic added)
- export products 

### Inventory Dashboard (Batch Editing)

URL: /inventory/
Purpose: A single place to view, filter, and edit key inventory values efficiently.

1. Fields to Display & Edit
Field	Editable	Notes
name	❌	Ingredient name (read-only)
unit_type	❌	For context (e.g., oz, g, unit)
current_stock	✅	Inline numeric input
reorder_point	✅	Inline numeric input
cost_per_unit	✅	Inline decimal input
price_per_unit	✅	Inline decimal input
case_size	✅	Optional, useful for bulk items
lead_time	✅	Optional, for ordering schedule
2. UX Features

✅ Search/filter by ingredient name or type (e.g., Milk, Flavor, Syrup).

📝 Inline editing using HTMX or a simple form → auto-saves changes on blur or with a “Save All” button.

📌 Sort by current_stock, reorder_point, or name to quickly spot issues.

⚠️ Optional highlighting for items below reorder point.

3. Backend Logic

New view: inventory_dashboard_view

Endpoint for bulk updates: /inventory/update/ (POST)

Will use a simple ModelFormSet or custom serializer for updating multiple Ingredient records in one go.

4. Future Enhancements

📈 Low-stock alert summaries at the top (e.g., “5 items below reorder point”).

🧾 Export inventory snapshot to CSV.

📊 Optional charts for trends once usage logging is mature.

This dashboard fits nicely alongside the recipes modal work you want to finish. Once the modal is complete, we can spin this dashboard up fairly quickly since the models are already in great shape.
