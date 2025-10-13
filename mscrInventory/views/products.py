from django.shortcuts import render
from mscrInventory.models import Product

def products_dashboard_view(request):
    products = Product.objects.select_related().prefetch_related("categories").order_by("name")
    return render(request, "products/dashboard.html", {"products": products})
