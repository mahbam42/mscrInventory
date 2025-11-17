# Bulk Add Stock

The **Bulk Add Stock** tool allows you to add multiple stock entries in a single workflow. This is faster and more reliable than updating each ingredient individually.

## How to Use Bulk Add Stock
1. Open the tool from the **Inventory Dashboard** or **Dashboard Quick Actions**.  
2. Add a row for each ingredient you received.  
3. Enter the quantity received and cost.  
4. (Optional) Include notes (lot number, supplier, etc.).  
5. Submit all entries at once.

## Behind the Scenes
- Each entry generates a **StockEntry** record.  
- The ingredient’s **current stock** is recalculated.  
- **Average cost** is updated based on weighted inputs.  

## When to Use Bulk Add
- Daily receiving  
- Weekly deliveries  
- Adjusting multiple items after inventory count  
- Updating costs after vendor price changes  

## Troubleshooting

### Stock Not Updating?
- Ingredient may be archived.  
- Ensure units match the ingredient’s defined UoM.  

### Average Cost Looks Wrong?
- Check if a previous entry had incorrect cost.  
- Re-run bulk update with corrected values.  

### Duplicate Stock Entries?
- Confirm entries before submitting.  
- Use CSV Import for large structured updates.  
