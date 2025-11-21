# Appendix A – Manual Testing

# Manual Test Plan

Use this as a high-level smoke/regression checklist. Unless otherwise noted, start from a fresh `python manage.py migrate` + demo data and remain logged in as a user with edit permissions.

## Authentication & Session Guardrails
- Log out, visit `/recipes/`, and confirm you are redirected to the login page; then log in and ensure you return to the requested URL.
- Attempt to POST to an HTMX endpoint (e.g., add ingredient to a recipe) while logged out; verify a 403 response with the expected “Forbidden” message.
- Confirm permission scoping: a user with `view_recipemodifier` but no ingredient permissions can open Modifier Explorer but cannot edit ingredients or save aliases.

## Dashboard Overview (`/`)
- Widgets populate: Active Products, Tracked Ingredients, Recent Imports, Recent Changes, Top Name-Your-Drink, Recent Warnings, Shortcuts, Quick Add/Import cards.
- Low stock + import failures raise warnings: create an ingredient below its reorder point and a failed import log, reload, and confirm both warnings appear.
- “Top Name-Your-Drink” tile links to orders search (URL contains `orders/?preset=`) and shows at least one named drink entry.
- Recent imports tile shows unmatched Square items when present.

## Orders Dashboard (`/orders/`)
- Default preset is 14 days and combines Square + Shopify orders.
- Platform filter: selecting Shopify hides Square orders; switching back restores both.
- Custom date range: choose preset “Custom,” set a start/end window that includes only mid-range orders, and verify only those appear; banner should note the custom window.
- Pagination: load with >25 orders, verify page 1 has 25, navigate to page 2 and confirm querystring retains filters.
- Open any order row and confirm `total_items` annotation equals the sum of item quantities.

## Recipes Dashboard (`/recipes/`)
- Grid headers are sortable: toggle ID, Product, Category, or Cost columns and confirm sort direction indicators update.
- Inactive products are hidden: deactivate a product, reload, and verify it disappears from the dashboard list and Base Item dropdown.
- Grid renders columns including product temperature. Search for “milk” and confirm matches bubble to the top while categories collapse appropriately.
- Edit modal opens from “Edit” and lists all ingredients with current quantities and units.
- Add an ingredient: choose from dropdown, enter quantity, click `+`; ingredient row appears immediately via HTMX without full page reload.
- Delete an ingredient: click ✕, accept confirmation, and ensure the row disappears instantly.
- Extend recipe: pick a base recipe in the modal, submit, and confirm ingredients clone into the current recipe.
- Live-reload: while server running, edit a template referenced by the page and verify auto-refresh.
- CSRF handling: repeat an add/delete while logged out to confirm safe 403 responses (no partial writes).

### Recipe CSV Export/Import
- Export CSV: click “📤 Export Recipes CSV,” open the file, and confirm each product appears once per ingredient with category name and COGS subtotal columns populated.
- Import (two-step modal if enabled): upload a CSV with valid + invalid rows, run dry-run, confirm invalid rows are reported without DB writes; rerun without dry-run to commit and verify recipe grid updates.

## Modifier Explorer (`/modifier-explorer/`)
- Load page with a `view_recipemodifier` user; confirm sections for Known, Alias token, Fuzzy, Unknown, and co-occurrence pairs.
- Classification filter: choose “Unknown” and verify matching products are hidden with a “Hiding N matching product(s)” banner; toggle “include known products” to reveal matches.
- Alias management: for an alias row, pick a mapped modifier from the select box and save; confirm selection persists after refresh.
- CSV export: load with sample data and request `?format=csv`; verify the response downloads with header containing `alias_label` and rows for each modifier insight.

## Inventory Management
- Bulk Add modal: open from inventory dashboard, add multiple stock entries, submit, and confirm StockEntry records and current stock totals update correctly.
- Inventory CSV export: trigger export, open file, and confirm ingredients, quantities, costs, and units are present.
- Inventory CSV import: upload a modified CSV, run in dry-run to view summary and validation errors, then import for real and check ingredient quantities and average cost adjustments reflect the file.
- Reorder point alert: set an ingredient below reorder level and ensure it appears in dashboard warnings and any “Inventory running low” lists.

## Imports Dashboard & Square/Shopify Integration
- Square CSV upload: submit a sample file with “Dry run” checked; expect redirect to imports dashboard, creation of a `square` ImportLog marked `dry-run`, stored file name ending in `-square.csv`, and buffered output displayed in the log detail.
- Secure temp file handling: verify uploaded Square CSV is stored in the configured `squareCSVs/` directory and removed after processing when appropriate.
- Unmapped Square items: after a Square import containing unknown items, open the “Unmapped items” tab, link an item to an existing product via “Link existing,” then create a new product using “Create from unmapped”; ensure mappings persist and import warnings decrease.
- Shopify sync/dry-run (if enabled): run the import or dry-run flow and confirm ImportLog captures run type, counts, and any unmatched items; verify no DB writes on dry-run.

## Reporting & Analytics
- Ingredient usage aggregation: trigger the report that rolls up ingredient usage across recipes/orders and confirm totals match expected counts.
- Dashboard metrics: verify calculated COGS and metric cards update after adjusting ingredient costs or recipe quantities.
- Export inventory/recipe/usage reports to CSV and ensure numerical columns retain precision (e.g., Decimal costs).

## Admin & User Management
- Admin access: log in as superuser, open Django admin, and confirm core models (Ingredient, Product, Recipe, RecipeModifier, ImportLog, Order) are visible.
- Permission enforcement: create a user without `change_ingredient` and confirm edit/delete buttons disappear while view-only pages still load.
- User creation: add a new user through the app’s user management flow, set a password, and verify login/logout works.

## Permissions Testing
| Group         | Can View           | Can Add/Edit                              | Can Import | Can Export | Can Access /admin | Can Delete |
| ------------- | ------------------ | ----------------------------------------- | ---------- | ---------- | ----------------- | ---------- |
| **Superuser** | ✅                  | ✅                                         | ✅          | ✅          | ✅                 | ✅          |
| **Manager**   | ✅                  | ✅                                         | ✅          | ✅          | ✅                 | ❌          |
| **Barista**   | ✅                  | ✅ (recipes, mods, ingredients, inventory) | ❌          | ❌          | ❌                 | ❌          |
| **Inventory** | ✅ (inventory only) | ✅ (inventory)                             | ❌          | ❌          | ❌                 | ❌          |
