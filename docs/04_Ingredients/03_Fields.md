# Ingredient Fields

| **Field** | **Description** |
|-----------|-----------------|
| **Name** | Display name used throughout the app |
| **Ingredient Type** | Category such as Milk, Syrup, Roast, Bagel, etc. |
| **Unit of Measure** | oz, ml, g, bag, scoop, etc. |
| **Cost per Unit** | Used to calculate COGS and inventory valuation |
| **Bag Size / Roast / Grind** | Auto-displayed for coffee and similar items |
| **Container Type**  | Defines the packaging subtype (Cup, Lid, Sleeve, Bag). |
| **Size Label** | Assigns descriptive size values; supports multiple labels per package. |
| **Temperature (Hot/Iced)** | Indicates which drink temperature this package applies to. |
| **Multiplier** | Converts default unit to the container’s effective usage size.  |
| **Expands To** | Links packaging to other required packaging components (e.g., a cup may expand to a lid + sleeve). |
| **Container (Inline Field)** | Points to the underlying container ingredient associated with this packaging option. |
| **Roast / Grind / Bag Size (Roast Inline)** | Additional metadata for coffee ingredients. |

**TIP:** Ensure cost is always entered per unit, not per package.
