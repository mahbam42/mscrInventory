# Low Stock Ingredients

The **Low Stock** view highlights ingredients that have fallen below their reorder point. These warnings appear both on the Dashboard and in the Inventory module.

## What Triggers Low Stock
- An ingredient’s calculated current stock drops below its `reorder_point` value. Or `usage` from last import times `lead time` will exceed `reorder_point`.
- Manual adjustments, bulk updates, or imports that reduce stock.
- Negative or inconsistent stock counts after CSV import.

## How to Use Low Stock Alerts
1. Open the **Dashboard** or **Inventory → Low Stock** (if available).  
2. Review the list of flagged ingredients.  
3. Click an ingredient name to open its detail modal.  
4. Enter new stock (e.g., after receiving a delivery).  
5. Save to update current inventory counts.

## Best Practices
- Review low-stock items at the start of each shift.  
- Update stock as soon as new items arrive.  
- Keep reorder points realistic—too low creates risk, too high inflates spent budget.  

**TIP:** Low-stock items often overlap with unmapped import issues. Always verify both.  
