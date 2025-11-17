# Orders Dashboard

The **Orders Dashboard** consolidates recent Shopify and Square orders into a single, unified view. It helps teams quickly review customer activity, custom drink trends, and imported item behavior.

## Key Features

### Unified Order Stream
- Displays both **Square** and **Shopify** orders.
- Combined view by default; platform filters allow narrowing to one source.
- Customizable date range with standard presets:
  - Today
  - Last 7 days
  - Last 14 days
  - Last 30 days
  - Custom date window

### Filters and Search
- Filter by platform (Square / Shopify)
- Search by product name or custom drink text
- Identify “Name Your Drink” items that appear frequently

### Order Details
Each order entry includes:
- Order timestamp
- Source (Square / Shopify)
- List of items with quantities
- Modifiers applied to each item
- Total item count (annotated for clarity)

### Pagination
- Large order volumes automatically paginate
- Navigation links preserve filter parameters

## “Name Your Drink” Integration
The Dashboard widget for **Top Name-Your-Drink** links directly into the Orders Dashboard filtered by the correct preset.

Use this feature to:
- Identify popular recurring custom drink names
- Validate whether new recipes or modifiers should be created
- Spot trends in seasonal or special‑request beverages

## Use Cases
- Reviewing unusual modifiers before running mapping updates
- Checking Square/Shopify consistency for newly added menu items
- Tracing the origin of unmapped or mis‑mapped items in imports
- Monitoring custom drink naming and usage frequency

## Troubleshooting

### Missing Orders?
- Confirm selected date range.
- Ensure platform filters are not hiding results.
- Check Shopify and Square export configurations.

### Unknown Modifier Appearing?
- Visit **Imports → Modifier Explorer** for classification.
- Review the associated product’s modifier groups.
- Check for spelling variations or Square menu discrepancies.

### Duplicate Orders?
- Ensure the same platform is not being imported twice.
- Verify the date range does not overlap across import sessions.

