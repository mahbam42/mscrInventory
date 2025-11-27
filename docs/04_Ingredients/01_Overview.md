# Ingredients Overview

Ingredients form the foundation of all recipes and products. Each ingredient record stores its name, type, unit of measure, unit cost, and optional descriptive fields such as roast level or bag size.

Ingredients must be maintained carefully, as they drive recipe accuracy, cost calculations, inventory counts, and reporting.

Key capabilities:
- Add, edit, or archive ingredients  
- Assign ingredient types  
- Track cost per unit  
- Associate packaging (cups, lids, sleeves, etc.)  
- Search and filter by category or status  

Packaging Ingredients

Some ingredients represent packaging components—such as cups, lids, sleeves, and bags. These items support richer metadata to ensure accurate inventory tracking and automatic “expands-to” behavior during usage calculations.

Packaging-related enhancements:

- Container Type – Defines the physical form (e.g., Cup, Lid, Sleeve, Bag).
- Size Label – Assigns a named size (e.g., 12oz, Large, Tall).
- Packaging Inline Editor – Provides a dedicated inline in the Ingredient admin page for configuring each packaging option:
  - Temperature (hot/iced)
  - Container (the underlying container ingredient)
  - Size Labels (supports multiple labels)
  - Multiplier
  - Optional expands to relationships (to ensure cups usage also includes coorisponding lid, sleeve, etc.)
