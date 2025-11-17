# Fetch Shopify CSV

The **Shopify Importer** is one of the most frequently used tools in the app. It pulls item-level sales data exported from Shopify via API, keeping recipes, products, and inventory aligned with what actually sold in the shop.

## How to Run a Shopify Import
1. Navigate to **Imports → Fetch Shopify**.  
2. Select the Date Range you need; the importer uses the start and end dates to pull every order in that window.
3. Click `Fetch Shopify`. The modal stays open with a progress indicator while the background task fetches the orders.
4. After completion, check the import log for any unmapped SKUs or modifiers that need resolution. Unmapped items render a warning inside the modal so you can link them with the right ingredients or recipes before the next sync.

## Follow-up
- Review the imported data on the **Imports History** screen to confirm totals and export the batch if you need a CSV backup.  
- If inventory quantities shift, refresh the Inventory dashboard so HTMX partials rerender with the updated on-hand amounts.  
- Schedule Shopify imports daily or weekly to keep pricing and modifier usage accurate for costing and purchasing workflows.
