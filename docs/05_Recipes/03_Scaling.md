# Understanding Dynamic Scaling

The app uses scaling ratios to automatically calculate ingredient quantities for different sizes.

### Example (Latte – Milk):
| **Size** | **Ratio** | **Milk Amount** |
|---------|-----------|------------------|
| Hot Small (12oz) | 1.0 | 8 oz |
| Iced Small (16oz) | 1.34 | 11 oz |
| Hot Large/XL (20oz) | 1.66 | 13.3 oz |
| Iced XL (32oz) | 2.68 | 21 oz |

Scaling ensures consistency and reduces repetitive data entry.

Ingredients like Milk and Coldbrew are dynamically scaled based on Modifiers added to a drink

**TIP:** Avoid rounding values prematurely — the system handles precision internally.
