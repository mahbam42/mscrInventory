# 🧾 MSCR Inventory App

A lightweight Django + HTMX–based inventory and recipe management system built for **Mike Shea Coffee Roasters**.  
Designed for small production environments, it blends **real-time usability** for staff with **robust data tracking** for analytics, costing, and reporting.

---

## 🚀 Key Features

### 📦 Inventory Management
- **Bulk Add Modal** – Adjust multiple stock entries at once with instant updates.  
- **CSV Import / Export** – Snapshot inventory for offline edits, then safely re-import changes.  
- **Average Cost Tracking** – Automatically updates ingredient cost using weighted averages.  
- **StockEntry Logging** – Every change (restock, spoilage, adjustment) creates a permanent audit trail.  

### 🍳 Recipe & Production Management
- **Dynamic COGS Calculation** – Real-time cost-of-goods for any recipe.  
- **Dry-Run Import Mode** – Validate recipes before writing to the database.  
- **Invalid Row Handling** – Separates valid and invalid data for easy correction.  
- **Modifier & Extras Logic** – Handles product modifiers, extras, and packaging relationships (e.g. cup → lid).  

### 🧑‍💼 Role-Based Permissions
- **Admin** – Full access, configuration, and reporting.  
- **Manager** – Data editing and user management (no frontend dashboard).  
- **Barista** – Simplified dashboard with real-time updates only.  
- Integrated with Django permissions and HTMX conditionals for adaptive UI visibility.

### 💻 User Interface
- **HTMX-Powered Dashboards** – Responsive modals, inline updates, and no reloads.  
- **Bootstrap 5 Layout** – Mobile-friendly and lightweight.  
- **Smart Filters** – Live search and category filtering.  
- **Contextual Navigation** – Permission-aware links and quick actions.  

### ⚙️ Management Commands
All commands support a `--dry-run` flag for safe testing.

| Command | Description |
|----------|--------------|
| `import_square_csv` | Parse and import daily Square sales exports. |
| `import_recipes_from_csv` | Bulk create or update recipes. |
| `import_chemistry` | Sync ingredient chemistry data from CSV. |
| `clean_empty_recipeitems` | Remove orphaned or duplicate recipe items. |
| `export_sqlite_backup` | Generate a timestamped CSV backup of all key tables. |
| `seed_dev_data` | Load optional fixtures for development. |

---

## 🧱 Architecture & Design Notes
- Built with **Django, HTMX, and Bootstrap** — minimal dependencies for maintainability.  
- CSV import/export doubles as an **internal API** for integrations and automation.  
- **Shopify integration** complete; **Doordash sync** in progress.  
- Modular data model: ingredients, modifiers, and packaging are fully relational.  
- Role-based dashboards ensure users see only relevant functionality.  

---

## 🧪 Testing & CI
- Continuous Integration via **GitHub Actions** — full test suite runs on every push to `main`.  
- Coverage includes imports, COGS calculations, permissions, and all core workflows.

---

## 🧭 Project Goals
To provide small-scale roasters with a **simple, auditable, and adaptable** system for managing production data —  
without the overhead of enterprise ERP platforms.
