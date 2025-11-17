
# Appendix B – Unmapped Items Usage

## Overview
Unmapped items are created when SquareImporter or ShopifyImporter cannot associate an incoming row with an existing product, ingredient, or modifier. This system is designed not only to catch inconsistencies in imports, but also to intelligently retain history and prevent duplicates.

---

## Unmapped-Item Flow

The importer performs the following steps:

1. **Initialize a fresh run state**
   - Each import session maintains a per-run log and counters.
   - All tracking resets at the start of each file.
   - When `dry_run=True`, all writes are rolled back, but the importer still performs all matching logic and logging.

2. **Row processing**
   - Each row is logged with contextual details.
   - The importer calls `_find_best_product_match`.
   - If no match is found, the system funnels into `_record_unmapped_item`.

3. **Price-point and shell item handling**
   - Generic menu shells such as “Barista’s Choice” are treated as unmatched unless pricing clarifies the intended product.
   - Seasonal or experimental variations properly surface as unmapped.

4. **Recording the unmapped item**
   - The importer normalizes its item/price-point pair.
   - Deduping occurs at both the per-run level and persistent DB level.
   - On live imports, normalization keys are used with `get_or_create` to avoid duplicates.
   - Reappearances update:
     - `last_seen`
     - `seen_count`
     - captured modifiers
     - resolution status

5. **Reopening resolved entries**
   - If an item previously resolved appears again with new context, the importer may reopen it rather than create a new entry.
   - This keeps history tidy but complete.

---

## Data Model & Persistence

`SquareUnmappedItem` includes:

- Source (Square/Shopify)
- Item type (Product, Ingredient, Modifier)
- Raw label values
- Normalized keys (for grouping)
- Snapshot of applied modifiers
- Reason for unmapped status
- Timestamps (`first_seen`, `last_seen`)
- Occurrence count
- Resolution metadata:
  - ignored status
  - link to actual Product/Ingredient/Modifier (if resolved)

**Uniqueness constraint:**  
One row per normalized item/variant ensures no duplicates are created.

**Helper methods** encapsulate:
- resolving
- reopening
- ignoring
- normalization logic

---

## Dashboard & Modal Experience

### Dashboard Behavior
- The Imports dashboard shows a warning button displaying the number of unresolved items.
- If no unmapped items exist, an “All items mapped” indicator is displayed.

### Modal and Full Dashboard
The same underlying view powers:
- the lightweight **HTMX modal**
- the full-page dashboard at `/dashboard/unmapped/`

These views include:
- filter controls
- per-item actions
- create/link forms
- pagination (for full view)

### Modal Features
- Quick summary of unresolved items
- Inline link/create forms
- “View Full Dashboard” for bulk actions or extended review

### Table Output
The shared table partial includes:
- Source
- Type
- Raw Name
- First/Last Seen
- Occurrences
- Actions (Link, Create, Ignore)

---

## Mapping Actions & Validation

### Linking
`LinkUnmappedItemForm` allows associating an item with:
- existing product  
- existing ingredient  
- existing modifier  

Upon save:
- `mark_resolved` is called
- updated metadata is returned
- the dashboard refreshes via HTMX

### Creating New Items
`CreateFromUnmappedItemForm`:
- tailors fields based on item type
- generates default SKUs when needed
- handles IntegrityErrors gracefully
  - duplicate names trigger user-friendly validation messages

### Bulk Actions
Bulk modes allow staff to:
- resolve all filtered items
- ignore all filtered items
- create placeholder records for batches

Bulk actions reuse:
- SKU generation helpers  
- `get_or_create` for ingredients  
- shared validation logic

---

## Admin & Coverage

In Django Admin, staff can view:
- All unmapped items
- Filters (source, type, ignored/resolved)
- Read-only historical fields
- Link/autocomplete relationships
- Custom admin actions:
  - resolve
  - ignore
  - reopen

ImportLog objects also include:
- summary previews
- stored file metadata
- associated warnings

---

## Regression Test Coverage

Automated tests include:
- dry-run safety
- handling variant unmapped items
- idempotent re-runs
- deduping behavior
- modal rendering
- full-page dashboard output
- bulk creation flows
- upload logging
- integration with ImportLog and related models

This ensures stable behavior across updates.

---

## Expected Behavior Recap

1. Run a Square import (use a Dry Run first).
2. Rows that cannot be matched become unmapped.
3. Live runs update:
   - occurrence count
   - timestamps
   - reopened vs. newly created entries
4. Staff review unmapped items using modal or dashboard.
5. Items are resolved by:
   - linking
   - creating a new record
   - marking as ignored
6. Bulk actions support efficient cleanup.
7. Admin provides a fallback UI for deeper workflow management.

Unmapped items ensure that all Square/Shopify data ultimately maps to a clean, unified dataset in the inventory system.
