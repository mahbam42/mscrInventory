# mscrInventory/views/inventory.py
from django.shortcuts import render

def inventory_dashboard_view(request):
    return render(request, "inventory/dashboard.html")
