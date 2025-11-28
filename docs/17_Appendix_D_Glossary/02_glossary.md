- ## A

- ## B

- ## C

    - ### Category
    : Simple taxonomy bucket for grouping Products. 
    - ### ContainerType {#ContainerType}
    : Reusable container description for packaging selections.

- ## D

- ## E 

- ## F

- ## G

- ## H

- ## I 

    - ### ImportLog
    : System generated to track file-based or API imports, counts, and outcomes.
    - ### Ingredient
    : Inventory tracked item with measurement, costing, and notes. **Ingredients** have subtypes to support properties for `Packaging` and `Roast Profiles`.

        - #### Packaging {#Packaging}
        : Ingredient subtype for cups, lids, and other packaging combos. 
            - **[Container Type](#ContainerType)** – Classifies the packaging (Cup, Lid, Sleeve, etc.).
            - **[Size Labels](#SizeLabel)** – Assign one or more labels (e.g., “12oz”, “Large”).
            - **Multiplier** – Used to convert the packaging’s base unit to the size used in inventory calculations with [Dynamic Scaling](../05_Recipes/03_Scaling.md).
            - **Temperature** – Whether this packaging is for hot or iced items.
            - **Expands To** – Optional mapping to other packaging components (e.g., a cup expands to include its matching lid).
        - #### Roast Profiles {#RoastProfile}
        : Retail coffee bag metadata tied to a roast ingredient. Used for mapping Modifiers to `Retail Bags` and `Bagged Coffee`.
            - Grind Type
            - Bag Size


    - ### IngredientType
    : Labels ingredients into logical families (roasts, packaging, etc.).
    - ### IngredientUsageLog
    : Log of ingredient usage per date. Typically created by the sync process that consumes OrderItems+RecipeItems and aggregates by ingredient.

- ## J 

- ## K

- ## L

- ## M
    - ### ModifierBehavior {#ModifierBehavior}
    : Normalized operations for manipulating recipe ingredients.
        Behaviors:
        - Add
        : Adds a Modifier to a [Order Item](#OrderItem)
        - Replace
        : Replaces an `Ingredient` by name or type. For example `Oat Milk` would replace `Whole Milk` in an Order Item.
        - Scale
        : Adjusts the quantity of an `Ingredient` or `Ingredient Type` in an Order Item. ie. `lite sugar` or `xtra flavor`.
        - Expand
        : For Modifiers that are compound ingredients. ie. `Dirty Chai` replaces the `Milk` with `Chai Concentrate` and adds an `Espresso Shot` to a drink
    - [Modifier Explorer](../06_Imports/04_ModifierExplorer.md)
    : Based on raw CSV data from Imports, helps you analyze and standardize modifier behavior across imported data. It groups modifiers into categories based on how they match existing records
- ## O
    - ### Order
    : High-level order pulled from connected commerce platforms.
    - ### Order Item {#OrderItem}
    : Line item belonging to an Order, optionally linked to a Product.
- ## P
    - [Packaging](#Packaging)
    - ### Product
    : Sellable menu item that links recipes, modifiers, and POS identifiers
- ## Q

- ## R
    - ### Recipe
    : Represents a single ingredient entry within a product's recipe.
      Each RecipeItem links one Product to one Ingredient, with a specific quantity, unit, and optional cost/price data. Together, all RecipeItems for a Product define that product's complete recipe and cost-of-goods basis.
    - ### RecipeModifier {#RecipeModifier}
    : Modifiers are extensions of Ingredients (e.g. milk options, syrups, extra shots). Each links to a base Ingredient but may  have its own cost, price, and [behavior](#ModifierBehavior).
    - ### RecipeModifierAlias {#RecipeModifierAlias}
    : Maps raw order modifiers to the normalized RecipeModifier via [Square Unmapped Items](../06_Imports/03_Unmapped_Items.md) or [Modifier Explorer](../06_Imports/04_ModifierExplorer.md).
    - [RoastProfile](#RoastProfile)
- ## S
    - ### SizeLabel {#SizeLabel}
    : Named portion sizes used when presenting packaging choices.
    - ### SquareUnmappedItem
    : Tracks Square rows that could not be resolved to an internal mapping via [Square Unmapped Items](../06_Imports/03_Unmapped_Items.md) .
    - ### StockEntry
    : Represents a restock via [`Bulk Add Stock`](../08_Inventory/02_BulkAdd.md) on the `Inventory Dashboard` event that updates weighted average cost.
- ## T

- ## U 
    - ### UnitType {#UnitType}
    : Measurement definition with a conversion ratio to a base unit.
- ## V

- ## W 

- ## X

- ## Y

- ## Z