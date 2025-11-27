# Ingredient Usage Reports

Ingredient usage reports calculate how much of each ingredient has been consumed over a specific date range.

## How Usage Is Calculated
Usage is derived from:
1. **Order data** imported from Square and Shopify.  
2. **Recipe definitions**, which determine ingredient quantities per product.  
3. **Scaling rules** (for multiple product sizes).  
4. **Modifier adjustments** (e.g., almond milk replacements).  

For each order, the system multiplies:
`ingredient quantity × number of items sold × size scaling`

## Use Cases
- Forecast purchasing needs  
- Identify high‑usage ingredients  
- Track cost changes over time  
- Validate recipe accuracy  

**TIP:** Usage anomalies often indicate a mismatch in recipe scaling or modifier rules.

## Units
Ingredient usage tables and exports display the unit type next to each quantity (for example, `12.000 oz`). Set a unit type on each ingredient to avoid the generic `units` label.
