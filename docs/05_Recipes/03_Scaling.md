# Understanding Dynamic Scaling

The app uses scaling ratios to automatically calculate ingredient quantities for different sizes.

### Example (Latte – Milk):
| **Size** | **Ratio** | **Milk Amount** |
|---------|-----------|------------------|
| Small (12oz) | 1.0 | 8 oz |
| Medium (16oz) | 1.33 | 10.6 oz |
| Large (20oz) | 1.66 | 13.3 oz |

Scaling ensures consistency and reduces repetitive data entry.

**TIP:** Avoid rounding values prematurely — the system handles precision internally.
