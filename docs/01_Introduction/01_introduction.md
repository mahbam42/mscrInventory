# Introduction

The **MSCR Inventory App** provides a unified, streamlined workflow for managing ingredients, recipes, products, orders, inventory, and imports across café and retail environments. It is designed to support both daily operations and long-term data accuracy, while remaining accessible to non-technical staff.

This manual describes the operational workflow for managers and authorized users who handle inventory updates, recipe maintenance, product management, user permissions, and data reconciliation through the web interface.

This guide is written for general staff, supervisors, and managers.  
Developer-only setup, installation, and technical notes have been removed from the main body of the manual and placed into the appendices. The intent is to keep the core documentation focused, practical, and easy to reference during daily operations.

---

## Architecture & Design Notes

The MSCR Inventory App is built with **Django**, **HTMX**, and **Bootstrap**, emphasizing clarity, maintainability, and minimal dependencies. These architectural choices allow the system to remain fast, flexible, and stable across multiple environments.

Key design principles:

* **Minimal Dependencies:**  
  Uses Django, HTMX, and Bootstrap — no frontend frameworks required.  

* **Relational, Structured Data Model:**  
  Ingredients, products, recipes, modifiers, and packaging are fully relational to ensure consistent reporting and precise cost calculations.

* **CSV-Driven Integration:**  
  CSV import/export serves both as operational tooling and an internal API for external systems (automation scripts, third-party integrations).

* **Square & Shopify Integration:**  
  Shopify integration is complete; DoorDash integration is in progress.  
  Direct Square and DoorDash API syncing (beyond CSV uploads) is planned.

* **Role-Based Views:**  
  Users only see relevant features based on their assigned permission group, keeping the UI clean and reducing confusion.

* **HTMX-Based UI:**  
  High-responsiveness without page reloads: edits, modals, updates, and lists refresh dynamically for a modern, lightweight interface.

---

## About This Manual

This manual is organized into the following major parts:

1. **Daily Operations & Dashboards** – overview of the dashboard, navigation systems, and daily workflows.  
2. **Core Data Management** – instructions for maintaining ingredients, recipes, products, and stock levels.  
3. **Imports & Data Reconciliation** – Square/Shopify import flows, unmapped item resolution, and modifier tools.  
4. **Advanced Tools** – reporting, user management, admin access.  
5. **Appendices** – manual testing, detailed unmapped item documentation, comparisons, and roadmap.

Each section is written to be self-contained, so users can jump directly to the workflow they're performing.

---

## Audience

This manual is intended for:

* **Managers & Supervisors** — inventory, product, and recipe changes; review reports; manage users.
* **Baristas & Staff** — view-only access; limited editing for ingredients, recipes, and inventory (depending on assigned role).
* **Inventory Personnel** — stock counts, adjustments, and purchasing prep.
* **Admins** — full access including Django Admin.

New users should begin with the **Quick Start Overview** for a high-level summary of daily responsibilities.

---

## Responsibilities & Safety Notes

This application directly influences cost calculations, product-recipe mapping, and overall reporting accuracy. When making updates:

* **Double-check ingredient names and units before saving.**
* **Avoid deleting items that are used elsewhere** (use Archive instead).
* **Use Dry Runs** when processing imports until you’re confident in the file.
* **Complete or cancel modals** before navigating to avoid data loss.
* **Maintain consistent naming conventions** for clean imports and reporting.

Following these guidelines ensures clean imports, accurate cost reporting, and smooth cross-system integration.

---

