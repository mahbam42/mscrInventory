from .navigation import NAV_ITEMS

def nav_links(request):
    return {
        "NAV_LINKS": [
            {"name": "Dashboard", "url": "/"},
            {"name": "Imports", "url": "/imports/"},
            {"name": "Recipes", "url": "/recipes/"},
            {"name": "Inventory", "url": "/inventory/"},
        ]
    }
