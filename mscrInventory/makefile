# ───────────────
# MSCR Inventory App
# Django + HTMX + Pytest
# ───────────────

# Default target
.DEFAULT_GOAL := help

# Variables
PYTHON := python3
MANAGE := $(PYTHON) manage.py
VENV := venv

# ───────────────
# Setup & install
# ───────────────

install: ## Install dependencies
	$(PYTHON) -m venv $(VENV)
	$(VENV)/bin/pip install --upgrade pip
	$(VENV)/bin/pip install -r requirements.txt

migrate: ## Run Django migrations
	$(MANAGE) migrate

seed: ## Optional: load seed data (if you add fixtures)
	$(MANAGE) loaddata seed.json

# ───────────────
# Run & reload
# ───────────────

run: ## Start the development server with auto-reload
	$(MANAGE) runserver

reload: ## Restart with browser reload middleware
	$(MANAGE) runserver_plus --noreload

shell: ## Open Django shell
	$(MANAGE) shell_plus

# ───────────────
# Testing
# ───────────────

test: ## Run pytest with coverage
	pytest --cov=mscrInventory --cov-report=term-missing

test-fast: ## Run pytest without DB teardown
	pytest -q --reuse-db

lint: ## Run code style checks (black + flake8)
	black --check .
	flake8 mscrInventory

format: ## Auto-format with black + isort
	black .
	isort .

# ───────────────
# Utilities
# ───────────────

check: ## Run Django’s system check
	$(MANAGE) check

makemigrations: ## Create new migrations
	$(MANAGE) makemigrations

collectstatic: ## Collect static files
	$(MANAGE) collectstatic --noinput

clean: ## Remove pycache and coverage files
	find . -type d -name "__pycache__" -exec rm -rf {} +
	rm -rf .pytest_cache .coverage htmlcov

# ───────────────
# Help
# ───────────────

help: ## Show this help message
	@echo ""
	@echo "MSCR Inventory Commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""
