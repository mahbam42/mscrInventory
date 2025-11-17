# Admin (Restricted Access)

The **Admin** section refers specifically to the Django Admin interface bundled with the MSCR Inventory App.  
This area provides direct access to the underlying database models and is intended **only for trained Managers and Admins**.

Because changes made here bypass some of the safety checks and convenience tools in the main UI, access is intentionally limited.

---

## What You Can Do in the Admin Area

The Django Admin exposes raw records for:
- **Ingredients**
- **Products**
- **Recipes**
- **Recipe Modifiers**
- **Ingredient Types**
- **Stock Entries**
- **Import Logs**
- **Square Unmapped Items**
- **Users and Groups (Permissions)**

From here you can:
- Correct data inconsistencies  
- Perform bulk edits not yet supported in the main interface  
- Review historical logs  
- Diagnose issues during import reconciliation  
- Inspect raw relationships between objects  

---

## When to Use Django Admin

Use Admin for:
- Troubleshooting unusual data inconsistencies  
- Cleaning up legacy entries  
- Reviewing unmapped items directly  
- Viewing ImportLog objects and raw CSV storage  
- Quick data inspection during development or QA  

Avoid using Admin for:
- Day‑to‑day ingredient or recipe updates  
- Product creation  
- Inventory adjustments  
- User creation (use **Manage Users** instead)

---

## Safety Notes

**WARNING:**  
Actions taken in Django Admin update the database immediately and permanently.

To ensure data integrity:

- **Do not delete** ingredients or recipes that appear in orders or imports  
- **Avoid editing primary keys** or relational links unless you fully understand downstream effects  
- **Use Archive instead of Delete** wherever possible  
- **Double‑check** ingredient type, units, and cost fields before saving  
- **Review all changes** in the main UI after editing records in Admin

---

## Access Requirements

Only users in the following groups may access Admin:

- **Admin**: Full access  
- **Manager**: Limited, read‑oriented access depending on configuration  

Barista, Inventory, and Pending users **cannot** enter the Django Admin interface.

---

## Troubleshooting

### Access Denied?
- Ensure your user account is assigned to **Admin** or **Manager**.
- Reload the page after permissions update.
- Log out and back in if the session does not refresh.

### Changes Not Appearing in Main UI?
- Some cached views require reload.
- Verify your edits match expected model fields.
- Inspect ImportLog or ingredient relationships if mappings seem incorrect.

---

