# Navigation Menu

The navigation menu appears at the top of the screen and contains the primary sections of the app. By default every signed-in user sees the following links:

| **Menu** | **Purpose** |
|---------|-------------|
| **Dashboard** | Summaries and quick links to recent activity. |
| **Imports** | Run import sessions, resolve unmapped items, and explore modifiers. |
| **Orders** | Unified Shopify + Square order history. |
| **Recipes** | View and edit recipe structures. |
| **Ingredients** | Manage ingredient definitions and costing inputs. |
| **Inventory** | Review inventory dashboards, counts, and archive history. |

Additional entries appear based on permissions:

- **Reporting** – visible when the user has the `mscrInventory.change_order` permission (granted to users who need access to aggregate sales and usage reporting).
- **Manage Users** and **Admin** – rendered inside the secondary admin menu when a user has the appropriate Django permissions. Use these links only when you need to adjust roles or access the Django Admin console.

**CAUTION:** The Admin area should only be used by managers or technical staff.