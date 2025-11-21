📍 Purpose
mscrInventory is a Django + HTMX application for managing ingredients, recipes, inventory, and imports for Mike Shea Coffee Roasters.
The system connects Ingredients → Products → Recipes → Modifiers to support costing, purchasing, production tracking, and automated imports.

⚙️ Stack Overview
Component	Description
Backend	Django (4.x+), Python 3.13
Frontend	HTMX + Bootstrap
Database	SQLite (local dev)
Version Control	GitHub → mahbam42/mscrInventory
Env Config	.env manages DEBUG, SECRET_KEY, ALLOWED_HOSTS
📁 Key Project Files
Path / File	Summary
mscrInventory/models.py	Ingredient, Product, Category, RecipeModifier
views.py	CRUD + HTMX endpoints
templates/mscrInventory/	Modals + partials
static/js/	HTMX event handlers
management/commands/	Import/export scripts, utilities
requirements.txt	Dependencies
🧩 Core Concepts

IngredientType / UnitType / Category — classification + measurement

RecipeModifier — expands or adjusts base ingredient usage

HTMX Modals — dynamic CRUD forms and dashboard interactions

Importers — normalize external POS data into Inventory models

🎯 Execution Discipline

When performing multi-step work (feature builds, refactors, migrations):

Execute work sequentially, marking each step: pending → in_progress → complete.

Only one step should ever be in_progress.

Communicate step state clearly in chat or commits.

Mandatory Standards

Documentation Updates Required

Any functional change (model, view, importer, command, or UI behavior) must update project documentation located in /docs/ and indexed in mkdocs.yml.

Permissions on New Commands

All new Django management commands must include appropriate permission checks and should integrate cleanly with the existing access-control patterns.

Tests Required for All Changes

Every code change must include new tests or updates to existing tests.

Begin with focused unit tests; expand to integration tests when behavior spans models, importers, or dashboards.

Docstrings Required on New Code

All new functions, classes, methods, utilities, and management commands must include concise, descriptive docstrings using standard Django/Python conventions.

Docstrings should describe:

Purpose

Inputs/args

Return value or side effects

Any assumptions or required context

🧠 Agent Instructions
Before Responding

Assume Django familiarity; avoid boilerplate.

Responses should be concise and include only the relevant code block.

Do not repeat material already covered in this document.

When the User Asks for Help

Common request types:

Debug

“Migration 0014 fails with KeyError: type.”
→ Investigate FK breakage or stale field references.

Refactor

“Simplify Ingredient.quantity logic.”
→ Provide minimal code diff.

UI

“HTMX modal save doesn’t refresh the list.”
→ Focus on triggers, swaps, templates.

When More Info Is Needed

Request only:

Filename(s)

Function/class

Goal (fix / add / refactor)

🔧 Common Commands
python manage.py runserver 0.0.0.0:8001
python manage.py makemigrations mscrInventory
python manage.py migrate
python manage.py import_chemistry

🧱 Debugging Standards

Use print() or logger.debug() for small probes.

Inspect DB via python manage.py dbshell.

Rebuild only the failing migration when cascading issues appear.

Provide short traceback summaries, not full logs unless asked.

🚀 Frequent Task Patterns
Task	Required Info	Output Format
Fix migration	Migration ID + short traceback	Minimal diff
Refactor model	Model or field	Replacement snippet
HTMX issue	Template + JS	Corrected snippet
Add test data	Models involved	Fixture JSON or Factory
🪶 Token & Response Discipline

Never output entire logs unless explicitly requested.

Summaries preferred: “0014 fails on RecipeModifier.type”.

Return precise, minimal code diffs.

Responses should remain concise and focused.