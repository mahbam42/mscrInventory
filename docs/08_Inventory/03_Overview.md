# Inventory Dashboard Overview

The Inventory dashboard centralizes ingredient, recipe, and stock data so the team can spot shortages, track inflow/outflow, and make purchasing decisions without leaving the dashboard. It highlights current on‑hand amounts and links each row to the underlying recipes and modifiers that drive those totals.

Two controls keep the workflow focused:

- **Add Case**: opens the modal that brings a new purchase case into the system, letting you specify the supplier, quantity, and cost while automatically updating linked inventory levels.
- **Update Row**: lets you refresh an existing entry when a quick adjustment is needed—such as a count correction or unit conversion—so the dashboard remains the single source of truth.

Because the Inventory dashboard is HTMX-driven, each control applies its change instantly and rerenders the relevant partial, keeping the rest of the page responsive and in sync.
