📍 Purpose
mscrInventory is a Django + HTMX app for managing ingredients, recipes, and inventory at Mike Shea Coffee Roasters.
It links Ingredients → Products → Recipes → Modifiers to support costing, purchasing, and production tracking.

⚙️ Stack Overview
| Component           | Description                                                                  |
| ------------------- | ---------------------------------------------------------------------------- |
| **Backend**         | Django (4.x +), Python 3.13                                                  |
| **Frontend**        | HTMX + Bootstrap                                                           |
| **Database**        | SQLite (local dev)                                                           |
| **Version Control** | GitHub → [mahbam42/mscrInventory](https://github.com/mahbam42/mscrInventory) |
| **Env Config**      | `.env` handles `DEBUG`, `SECRET_KEY`, `ALLOWED_HOSTS`                        |


📁 Key Project Files
PathSummarymscrInventory/models.pyIngredient, Product, Category, RecipeModifier, etc.views.pyCRUD + HTMX endpointstemplates/mscrInventory/Modals + partialsstatic/js/HTMX event scriptsmanagement/commands/Import/export + seed scriptsrequirements.txtPython dependencies

🧩 Core Concepts


IngredientType / UnitType / Category: classification + measurement


RecipeModifier: expands or adjusts base quantities


HTMX Modals: dynamic add/edit forms


⚙️ Execution Discipline
When performing multi-step work (e.g., migrations, refactors, imports, feature builds):

Execute steps sequentially.
Assign a status to each step: pending, in_progress, complete.
Exactly one step should be in_progress until all are complete.

Document step status clearly in chat or commits, e.g.
✅ Step 1 – Add field → complete  
🔄 Step 2 – Update serializer → in_progress  
⏸️ Step 3 – Write tests → pending

Build tests after implementation.

Start with specific, local tests targeting changed code.

Expand to broader integration tests once confident.

Maintain a fast feedback loop and minimize regression risk.


🧠 Agent Instructions
✅ Before Responding


Assume Django familiarity — skip boilerplate.


Limit responses to the smallest relevant code block.


Don’t restate info already summarized here.


Expand only when explicitly asked.


💡 When the User Asks for Help
Expect one of these formats:
# Debug
Migration 0014 fails with KeyError: 'type'
→ Check field renames or missing FKs in RecipeModifier.

# Refactor
Simplify Ingredient.quantity logic for readability.
→ Return minimal code diff.

# UI
HTMX form doesn’t update Ingredient list after save.
→ Focus on event triggers and partial re-renders.

🧾 Ask For
If context is unclear, request only:


File name(s)


Function/class name(s)


Clear goal (e.g., “fix”, “add feature”, “refactor”)



🔧 Common Commands
python manage.py runserver 0.0.0.0:8001
python manage.py makemigrations mscrInventory
python manage.py migrate
python manage.py import_chemistry


🧱 Debugging Standards


Use print() or logger.debug() for checks.


Inspect schema via python manage.py dbshell.


Rebuild only the failing migration when errors cascade.



🚀 Frequent Tasks
TaskInfo RequiredOutput FormatFix migrationMigration ID + tracebackMinimal code diffRefactor modelClass snippetReplacement codeHTMX bugTemplate + JS snippetCorrected JSAdd test dataModel namesFixture JSON

🪶 Token Discipline


Never include entire logs unless asked.


Always name the file and error instead.


Use concise traceback summaries.


Prefer: “0014 migration fails on RecipeModifier.type” → not full traceback.


Return concise code diffs, not whole files.
