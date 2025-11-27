# Adding or Editing Ingredients

## Add a New Ingredient
1. Navigate to **Inventory → Ingredients**.  
2. Click **Add Ingredient (+)**.  
3. Enter the ingredient **name**, **type**, **unit**, and **cost per unit**.  
4. (Optional) Add details such as **roast**, **grind**, or **bag size**.  
5. Click **Save**.

## Edit an Existing Ingredient
1. Open the Ingredients list.  
2. Click the **Edit (✎)** icon next to the ingredient.  
3. Update cost, type, or metadata.  
4. Save changes.

### Editing Packaging for a Cup, Lid, or Other Container

If an ingredient is a type of packaging, an additional Packaging Options inline section will appear when editing it.

Within this inline you can configure:

- Container Type – Classifies the packaging (Cup, Lid, Sleeve, etc.).
- Size Labels – Assign one or more labels (e.g., “12oz”, “Large”).
- Multiplier – Used to convert the packaging’s base unit to the size used in inventory calculations.
- Temperature – Whether this packaging is for hot or iced items.
- Expands To – Optional mapping to other packaging components (e.g., a cup expands to include its matching lid).

After adjustments, click `Save`.
The system will automatically update downstream mappings and usage logic.

### Editing Coffee Roasts

If the ingredient is a Coffee Roast, a dedicated inline will appear with fields for:

- Roast Level
- Grind Type
- Bag Size

These fields are automatically displayed based on ingredient type and are used for reporting, recipe costs, and importer logic.

## Archiving Ingredients
- Use **Archive** instead of Delete.  
- Archived ingredients are hidden from active lists but preserved in historical records.

**CAUTION:** Do not delete ingredients used in recipes.

