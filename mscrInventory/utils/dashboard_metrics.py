from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from django.core.cache import cache
from django.db.models import F
from django.urls import reverse

from mscrInventory.models import (
    ImportLog,
    Ingredient,
    Product,
    RecipeModifier,
    SquareUnmappedItem,
)

STAT_COUNT_CACHE_KEY = "dashboard:stat_counts"
LOW_STOCK_CACHE_KEY = "dashboard:low_stock"
CACHE_TIMEOUT = 300  # 5 minutes
LOW_STOCK_LIMIT = 5
RECENT_IMPORT_LIMIT = 4
ACTIVITY_LIMIT = 6
WARNING_LIMIT = 5


@dataclass
class ImportStatus:
    label: str
    badge_class: str


def get_stat_counts() -> Dict[str, int]:
    cached = cache.get(STAT_COUNT_CACHE_KEY)
    if cached:
        return cached

    counts = {
        "active_products": Product.objects.filter(active=True).count(),
        "ingredients": Ingredient.objects.count(),
        "unmapped": SquareUnmappedItem.objects.filter(
            resolved=False,
            ignored=False,
        ).count(),
    }
    cache.set(STAT_COUNT_CACHE_KEY, counts, CACHE_TIMEOUT)
    return counts


def get_low_stock_summary(limit: int = LOW_STOCK_LIMIT) -> Dict[str, Any]:
    cache_key = f"{LOW_STOCK_CACHE_KEY}:{limit}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    qs = Ingredient.objects.filter(
        reorder_point__gt=0,
        current_stock__lte=F("reorder_point"),
    )
    summary = {
        "total": qs.count(),
        "items": list(
            qs.order_by("current_stock").values(
                "id",
                "name",
                "current_stock",
                "reorder_point",
            )[:limit]
        ),
    }
    cache.set(cache_key, summary, CACHE_TIMEOUT)
    return summary


def build_stat_cards(
    stat_counts: Dict[str, int], low_stock_summary: Dict[str, Any]
) -> List[Dict[str, Any]]:
    return [
        {
            "title": "Active Products",
            "value": stat_counts["active_products"],
            "description": "Menu items currently for sale",
            "icon": "bi-bag-check",
            "cta": {"label": "View Orders", "url": reverse("orders_dashboard")},
        },
        {
            "title": "Tracked Ingredients",
            "value": stat_counts["ingredients"],
            "description": "Inventory items with stock levels",
            "icon": "bi-archive",
            "cta": {"label": "Inventory", "url": reverse("inventory_dashboard")},
        },
        {
            "title": "Unmapped Items",
            "value": stat_counts["unmapped"],
            "description": "Square rows needing review",
            "icon": "bi-exclamation-triangle",
            "highlight": stat_counts["unmapped"] > 0,
            "cta": {
                "label": "Resolve",
                "url": reverse("imports_unmapped_items"),
            },
        },
        {
            "title": "Low Stock Alerts",
            "value": low_stock_summary["total"],
            "description": "At or below reorder point",
            "icon": "bi-thermometer-half",
            "items": low_stock_summary["items"],
            "cta": {"label": "Restock", "url": reverse("inventory_dashboard")},
        },
    ]


def get_recent_imports(limit: int = RECENT_IMPORT_LIMIT) -> List[Dict[str, Any]]:
    logs = ImportLog.objects.order_by("-created_at").select_related("uploaded_by")[:limit]
    results: List[Dict[str, Any]] = []
    for log in logs:
        status = determine_import_status(log)
        results.append(
            {
                "source": log.get_source_display(),
                "run_type": log.get_run_type_display(),
                "created_at": log.created_at,
                "rows_processed": log.rows_processed,
                "matched": log.matched_count,
                "unmatched": log.unmatched_count,
                "status": status.label,
                "badge": status.badge_class,
                "summary": log.summary,
            }
        )
    return results


def determine_import_status(log: ImportLog) -> ImportStatus:
    if not log.finished_at:
        return ImportStatus("Running", "bg-info text-dark")
    if log.error_count:
        return ImportStatus("Failed", "bg-danger")
    if log.unmatched_count:
        return ImportStatus("Partial", "bg-warning text-dark")
    return ImportStatus("Success", "bg-success")


def get_activity_feed(limit: int = ACTIVITY_LIMIT) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []

    for ingredient in Ingredient.objects.order_by("-last_updated")[:limit]:
        events.append(
            {
                "kind": "Ingredient",
                "name": ingredient.name,
                "timestamp": ingredient.last_updated,
                "detail": "Stock level updated",
            }
        )

    for modifier in RecipeModifier.objects.order_by("-updated_at")[:limit]:
        events.append(
            {
                "kind": "Modifier",
                "name": modifier.name,
                "timestamp": modifier.updated_at,
                "detail": f"Behavior: {modifier.get_behavior_display()}",
            }
        )

    for import_log in ImportLog.objects.order_by("-created_at")[:limit]:
        events.append(
            {
                "kind": "Import",
                "name": f"{import_log.get_source_display()} run",
                "timestamp": import_log.created_at,
                "detail": f"{import_log.rows_processed} rows processed",
            }
        )

    events = [e for e in events if e["timestamp"]]
    events.sort(key=lambda item: item["timestamp"], reverse=True)
    return events[:limit]


def get_quick_actions() -> List[Dict[str, Any]]:
    return [
        {
            "label": "Add Ingredient",
            "description": "Track a new inventory item",
            "hx_get": reverse("ingredient_create_modal"),
            "hx_target": "#modal-body",
            "hx_trigger": "click",
            "icon": "bi-plus-circle",
        },
        {
            "label": "Upload CSV",
            "description": "Run an import or dry run",
            "url": reverse("imports_dashboard"),
            "icon": "bi-file-earmark-arrow-up",
        },
        {
            "label": "Sync Square",
            "description": "Trigger the latest order sync",
            "url": reverse("imports_dashboard") + "#square-sync",
            "icon": "bi-arrow-repeat",
        },
    ]


def get_shortcuts() -> List[Dict[str, Any]]:
    return [
        {"label": "Products", "url": reverse("orders_dashboard"), "icon": "bi-basket"},
        {"label": "Ingredients", "url": reverse("ingredients_dashboard"), "icon": "bi-droplet"},
        {"label": "Recipes", "url": reverse("recipes_dashboard"), "icon": "bi-journal-text"},
        {"label": "Inventory", "url": reverse("inventory_dashboard"), "icon": "bi-box-seam"},
        {"label": "Imports", "url": reverse("imports_dashboard"), "icon": "bi-cloud-arrow-down"},
        {"label": "Reports", "url": reverse("reporting_dashboard"), "icon": "bi-graph-up"},
    ]


def get_warning_items(
    low_stock_summary: Dict[str, Any],
    stat_counts: Dict[str, int],
    recent_imports: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []

    if low_stock_summary["total"]:
        warnings.append(
            {
                "title": "Inventory running low",
                "detail": f"{low_stock_summary['total']} ingredients are at reorder levels",
                "url": reverse("inventory_dashboard"),
            }
        )

    if stat_counts["unmapped"]:
        warnings.append(
            {
                "title": "Unmapped Square items",
                "detail": f"{stat_counts['unmapped']} recent orders need attention",
                "url": reverse("imports_unmapped_items"),
            }
        )

    for import_entry in recent_imports:
        if import_entry["status"] in {"Failed", "Partial"}:
            warnings.append(
                {
                    "title": f"Import {import_entry['status'].lower()}",
                    "detail": (
                        f"{import_entry['source']} import processed {import_entry['rows_processed']} rows"
                    ),
                    "url": reverse("imports_dashboard"),
                }
            )

    return warnings[:WARNING_LIMIT]

