from .navigation import NAV_ITEMS

def navigation_context(request):
    return {"NAV_ITEMS": NAV_ITEMS}

def nav_links(request):
    return {
        "NAV_LINKS": [
            {"name": "Dashboard", "url": "/"},
            {"name": "Imports", "url": "/imports/"},
            #{"name": "Recipes", "url": "/recipes/"},
            {"name": "Products", "url": reverse("products_dashboard")},
            #{"name": "Inventory", "url": "/inventory/"},
        ]
    }
