# Imports Overview

The **Imports** section manages all inbound data from Square, Shopify, and CSV-based internal tools.  
It is the central hub for maintaining accurate mappings, reconciling mismatched items, and keeping the inventory and recipe systems aligned with real-world sales.

Imports support:

- Square CSV uploads  
- Shopify imports   
- Bulk import history review  
- Modifier classification and analysis  
- Unmapped item resolution (with modal or full-page dashboard)

Additional CSV Imports are handled on Dashboards:
- Ingredient CSV uploads  
- Inventory CSV updates ∂

Accurate imports ensure:

- Correct recipe and product usage reporting
- Clean naming conventions
- Accurate cost-of-goods tracking
- Smooth cross-platform data sync

## Product matching guardrails

Square and Shopify imports evaluate exact matches before partial or fuzzy matches. When multiple candidates overlap in a composed line (for example, "Small Iced Latte – Banana Bread – Oat Milk"), partial fallbacks deliberately choose the shortest matching product name so the base drink anchors the line and modifiers remain intact. Exact matches for the full product name still take priority over these partial fallbacks.
