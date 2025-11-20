# Reporting

The **Reporting** module provides visibility into ingredient usage, cost of goods (COGS), inventory valuation, and operational insights across your café or retail environment. These reports help managers make data‑driven decisions regarding purchasing, pricing, inventory, and recipe management.

Reporting pulls from:
- Ingredient records  
- Recipe structures  
- Inventory stock entries  
- Order histories  
- Square and Shopify imports  

Accurate reporting depends on clean recipes, well‑maintained ingredients, and properly resolved imports.

## Order-date alignment

COGS trend and ingredient usage totals are calculated by the order date, not the import timestamp. During imports, each order’s business-day date is stored on the related `IngredientUsageLog` entries so that:

- Multi-day imports still land on the correct service date.
- The COGS trend table reflects true day-to-day consumption.
- Usage totals always match what guests purchased on that day, even if the data was synced later.

## Leaderboard deltas

The reporting dashboard highlights rank changes for top-selling products and modifiers. Current ranks are compared to the immediately preceding window of the same length (e.g., the prior day when viewing a single date) so you can spot movers, decliners, and new entries at a glance.
