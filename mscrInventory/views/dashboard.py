# Create your views here.
# mscrInventory/views.py
from django.shortcuts import render
from django.utils.timezone import now
from django.db.models import Sum, F
from decimal import Decimal
import datetime

from .models import Order, OrderItem, Product, Ingredient

def dashboard_view(request):
    # Use today (Eastern) as default date
    today = now().date()
    selected_date_str = request.GET.get("date")
    if selected_date_str:
        selected_date = datetime.date.fromisoformat(selected_date_str)
    else:
        selected_date = today

    # --- Summary Stats ---
    orders_qs = Order.objects.filter(order_date__date=selected_date)
    total_orders = orders_qs.count()
    total_revenue = orders_qs.aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")

    unmapped_products_count = Product.objects.filter(name__startswith="Unmapped:").count()
    low_stock_ingredients = Ingredient.objects.filter(current_stock__lt=F("reorder_point"))

    # --- Top Products ---
    top_products = (
        OrderItem.objects
        .filter(order__order_date__date=selected_date, product__isnull=False)
        .values("product__name", "product__sku")
        .annotate(total_qty=Sum("quantity"), total_sales=Sum(F("quantity") * F("unit_price")))
        .order_by("-total_qty")[:5]
    )

    # --- Unmapped Products ---
    unmapped_products = Product.objects.filter(name__startswith="Unmapped:")

    context = {
        "selected_date": selected_date,
        "total_orders": total_orders,
        "total_revenue": total_revenue,
        "unmapped_products_count": unmapped_products_count,
        "low_stock_ingredients": low_stock_ingredients,
        "top_products": top_products,
        "unmapped_products": unmapped_products,
    }

    return render(request, "dashboard.html", context)
