# Unmapped Items Dashboard

Unmapped items appear when the importer cannot match a Square or Shopify row to an existing product, ingredient, or modifier.

Common reasons include:

- Misspellings  
- New seasonal drinks  
- Visibility differences between Square and the Inventory App  
- Price-point variants not recognized by the system  
- Missing modifier groups or recipe definitions  

## How to Resolve Unmapped Items
1. Go to **Imports → Unmapped Items**.  
2. Review the list (modal or full-page).  
3. For each unmapped row:
   - **Link to Existing** product/ingredient/modifier  
   - **Create New** record  
   - **Mark as Ignored** if not relevant  
4. Confirm your action.  
5. Unmapped count updates immediately.

## Unmapped Items Modal
The modal presents:
- Source (Square or Shopify)  
- Item type (Product, Ingredient, Modifier)  
- Raw name from import  
- Suggested matches (if any)  
- Link/Create actions  

## Full Unmapped Items Dashboard
Includes:
- Filters (type/source/date)  
- Pagination  
- Bulk actions  
- Links to record creation  
- “Open in Modal” options  

## Technical Internals
For a complete explanation of:
- how unmapped items are normalized  
- how duplicates are prevented  
- when rows reopen after being resolved  
- how occurrence tracking works  
- how Ignore/Resolve/Create logic behaves  

**See Appendix B – Unmapped Items Usage.**
