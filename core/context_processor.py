from .navigation import NAV_ITEMS

def navigation_context(request):
    return {"NAV_ITEMS": NAV_ITEMS}
