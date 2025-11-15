# core/context_processors.py
from django.urls import reverse, NoReverseMatch

def navigation_links(request):
    """
    Returns a list of visible navigation items.
    Skips any that can't be reversed, so missing routes don't break templates.
    """
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return {"nav_links": []}

    nav_items = [
        {"name": "Dashboard", "url_name": "dashboard"},
        {"name": "Imports", "url_name": "imports_dashboard"},
        {"name": "Orders", "url_name": "orders_dashboard"},
        {"name": "Recipes", "url_name": "recipes_dashboard"},
        {"name": "Ingredients", "url_name": "ingredients_dashboard"},
        {"name": "Inventory", "url_name": "inventory_dashboard"},
    ]

    if user.has_perm("mscrInventory.change_order"):
        nav_items.append({"name": "Reporting", "url_name": "reporting_dashboard"})

    if user.has_perm("auth.change_user"):
        nav_items.append({"name": "Manage Users", "url_name": "manage_users"})
    if user.is_staff:
        nav_items.append({"name": "Admin", "url_name": "admin:index"})

    links = []
    for item in nav_items:
        try:
            links.append({
                "name": item["name"],
                "url": reverse(item["url_name"])
            })
        except NoReverseMatch:
            # Silently skip if not defined yet
            continue

    return {"nav_links": links}


def admin_link(request):
    """Expose the Django admin link globally."""

    return {"admin_url": "/admin/"}

# from .navigation import NAV_ITEMS

# def navigation_context(request):
#     return {"NAV_ITEMS": NAV_ITEMS}

# def nav_links(request):
#     return {
#         "NAV_LINKS": [
#             {"name": "Dashboard", "url": "/"},
#             {"name": "Imports", "url": "/imports/"},
#             #{"name": "Recipes", "url": "/recipes/"},
#             {"name": "Products", "url": reverse("products_dashboard")},
#             #{"name": "Inventory", "url": "/inventory/"},
#         ]
#     }
