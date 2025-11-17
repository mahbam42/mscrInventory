# Upload Square CSV

The **Square Importer** is one of the most frequently used tools in the app. It processes item-level sales data exported from Square.

## How to Run a Square Import
1. Navigate to **Imports → Square Import**.  
2. Upload a Square CSV file.  
3. (Optional) Check **Dry Run** to simulate the import.  
4. Click **Upload**.  
5. Review the import summary including created, updated, skipped, or unmapped rows.

### Dry Run Mode
- Parses the full CSV  
- Performs all matching logic  
- Logs warnings and unmapped items  
- **Does not write anything** to the database  

This is ideal for checking file structure before running a full import.

## Import Results Summary
After processing a file, the importer displays:

- Number of products matched  
- Number of modifiers detected  
- Items created or updated  
- Items skipped or ignored  
- Total unmapped items (with button to resolve)
- Any warnings or validation errors

**TIP:** Always perform a Dry Run for new menus or seasonal items.
