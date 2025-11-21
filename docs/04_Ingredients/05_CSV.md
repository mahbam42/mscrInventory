# Bulk Editing and CSV Import

Large ingredient updates can be made with the **Ingredient CSV Importer**.

## Workflow
1. On the **Ingredients Dashboard** click **Export CSV** to download a round-trippable file with headers.
2. Or open **Import CSV** → **Download Template** to grab a clean header-only file.
3. Upload your CSV from the import modal and preview valid/invalid rows.
4. Confirm to apply updates or creates; the table refreshes automatically.

## Template Columns
- `id` (existing ingredient id; leave blank to create)
- `name`
- `type_id`/`type_name`
- `unit_type_id`/`unit_type_name`
- `case_size`
- `reorder_point`
- `average_cost_per_unit`
- `lead_time`
- `notes`

## Best Uses
- Updating multiple costs or reorder points
- Adding new seasonal items without using the form repeatedly
- Cleaning up inconsistent types or units

**CAUTION:** Rows match by `id` first, then by `name` if no id is provided.
