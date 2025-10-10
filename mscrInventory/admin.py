# admin.py (top of file)
import io
import csv
import datetime
import zipfile
from decimal import Decimal
from django.http import HttpResponse
from django.contrib import admin

from .models import (
    Product, Ingredient, StockEntry, RecipeItem,
    Order, OrderItem, IngredientUsageLog
)
from .utils.reports import cogs_by_day, usage_detail_by_day


# Register your models here.
class RecipeItemInline(admin.TabularInline):
    model = RecipeItem
    extra = 1
    autocomplete_fields = ['ingredient']
    fields = ('ingredient', 'quantity_per_unit', 'unit_type')
    show_change_link = True


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'category', 'active')
    list_filter = ('category', 'active')
    search_fields = ('name', 'sku')
    inlines = [RecipeItemInline]   # 👈 use the inline class defined above
    ordering = ['name']

@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'unit_type', 'current_stock', 'average_cost_per_unit',
        'reorder_point', 'lead_time', 'last_updated'
    )
    list_filter = ('unit_type',)
    search_fields = ('name',)     

from .models import Order, OrderItem

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'quantity', 'unit_price')
    can_delete = False

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'platform', 'order_date', 'total_amount', 'synced_at')
    list_filter = ('platform', 'order_date')
    search_fields = ('order_id',)
    inlines = [OrderItemInline]
    readonly_fields = ('order_id', 'platform', 'order_date', 'total_amount', 'data_raw', 'synced_at')
    ordering = ['-order_date']

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'product', 'quantity', 'unit_price')
    list_filter = ('product',)
    search_fields = ('order__order_id', 'product__name', 'product__sku')
    ordering = ['-order__order_date']
    readonly_fields = ('order', 'product', 'quantity', 'unit_price')

class UnmappedProductFilter(admin.SimpleListFilter):
    title = 'Mapping Status'
    parameter_name = 'mapped'

    def lookups(self, request, model_admin):
        return (
            ('mapped', 'Mapped'),
            ('unmapped', 'Unmapped'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'mapped':
            return queryset.exclude(name__startswith='Unmapped:')
        if self.value() == 'unmapped':
            return queryset.filter(name__startswith='Unmapped:')
        return queryset

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('sku', 'name', 'category')
    list_filter = (UnmappedProductFilter, 'category')
    search_fields = ('sku', 'name')
