# Exporting Reports (In Development)

The reporting dashboard is currently an interactive, on-screen experience. Views such as usage, COGS, and inventory snapshots re
nder charts and cards that respond to the selected date window, but they do **not** provide CSV downloads yet.

## Current Workflow
1. Open the reporting dashboard.
2. Adjust the date filters or presets to show the period you need.
3. Review the widgets/cards directly in the browser.

If you need to perform spreadsheet analysis, copy the on-screen values or take screenshots until CSV export endpoints are implem
ented.

## Roadmap
- CSV export buttons will appear once dedicated download views are added to `mscrInventory/views/reporting.py`.
- When available, exports will include the same precision as the on-screen metrics (ingredient units, extended costs, etc.).
