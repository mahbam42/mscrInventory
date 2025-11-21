# Appendix A – Automated Test Suite

Our [`tests/`](https://github.com/mahbam42/mscrInventory/tree/main/tests) directory provides automated regression coverage across the app. The suite uses `pytest` with factory fixtures (`tests/factories.py`, `tests/conftest.py`) to spin up lightweight data for each scenario.

## Coverage snapshot
- Views & HTMX flows (auth, dashboard, orders, recipes, inventory, user management)
- Importers (Square, Shopify, CSV), dry-run behavior, and data hygiene tools
- Reporting utilities and dashboard metrics
- Model behaviors, modifiers, and recipe math (including packaging and COGS)
- Templates and permission enforcement regressions
- Migration cleanup and critical utilities

## How to run
From the repo root, run:
```bash
pytest
```
This executes the full regression suite locally; CI runs the same entry point to guard releases.

## Automation Log
The test suite runs automatically with every push to `main` on GitHub. Results can be viewed on [GitHub](https://github.com/mahbam42/mscrInventory/actions/workflows/main.yml). 

