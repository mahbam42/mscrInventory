# admin.py (top of file)
import io
import csv
import datetime
import zipfile
from decimal import Decimal
from django.http import HttpResponse
from django.contrib import admin

from .models import (
    Product,
    Ingredient,
    RecipeItem,
    RecipeModifier,
    Category,
    Coffee,
    Order,
    OrderItem,
    IngredientUsageLog,
    StockEntry,
    ImportLog,
    IngredientType,
    UnitType
)
from .utils.reports import cogs_by_day, usage_detail_by_day


# Register your models here.

@admin.register(StockEntry)
class StockEntryAdmin(admin.ModelAdmin):
    list_display = (
        "ingredient",
        "quantity_added",
        "cost_per_unit",
        "source",
        "note",
        "date_received",
    )
    list_filter = ("source", "ingredient")
    search_fields = ("ingredient__name", "note")
    ordering = ("date_received",)
    readonly_fields = ("date_received",)

    fieldsets = (
        (None, {
            "fields": (
                "ingredient",
                ("quantity_added", "cost_per_unit"),
                ("source", "note"),
                "date_received",
            )
        }),
    )

    def has_add_permission(self, request):
        # Optional: prevent manual entry through admin — keep it data-driven
        return False

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
    
class RecipeItemInline(admin.TabularInline):
    model = RecipeItem
    extra = 1
    autocomplete_fields = ['ingredient']
    fields = ("ingredient", "quantity", "unit", "cost_per_unit", "price_per_unit")
    #fields = ('ingredient', 'quantity_per_unit', 'unit_type')
    show_change_link = True

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)

#Subclass of Product for Bagged Coffee Properties 
class CoffeeInline(admin.StackedInline):
    model = Coffee
    extra = 0
    can_delete = False
    verbose_name_plural = "Coffee Details"
    
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category_list", "active", "created_at")
    list_filter = ("active", "categories")

    def get_inline_instances(self, request, obj=None):
        """
        Dynamically include Coffee inline when editing Coffee products.
        """
        CoffeeInlines = []
        if obj and hasattr(obj, "coffee"):
            CoffeeInlines.append(CoffeeInline(self.model, self.admin_site))
        return CoffeeInlines

    search_fields = ('name', 'sku')
    filter_horizontal = ("modifiers",)  # 👈 adds nice M2M selector widget
    inlines = [RecipeItemInline, ]   # 👈 use the inline class defined above
    ordering = ['name']

    def category_list(self, obj):
        return ", ".join(c.name for c in obj.categories.all())
    category_list.short_description = "Categories"

@admin.register(IngredientType)
class IngredientTypeAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    ordering = ("name",)

@admin.register(UnitType)
class UnitTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "abbreviation", "conversion_to_base")
    search_fields = ("name", "abbreviation")
    ordering = ("name",)

class StockEntryInline(admin.TabularInline):
    model = StockEntry
    extra = 0
    readonly_fields = ("quantity_added", "cost_per_unit", "source", "note", "date_received")
    can_delete = False

@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = (
        "name", "type", "unit_type", "current_stock", "average_cost_per_unit",
        "reorder_point", "lead_time", "last_updated"
    )
    list_filter = ("type", "unit_type",)
    search_fields = ("name",)
    inlines = [StockEntryInline]

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

@admin.register(RecipeModifier)
class RecipeModifierAdmin(admin.ModelAdmin):
    """
    Admin interface for RecipeModifier, supporting new DB-driven behavior logic.
    Includes JSON editing for target_selector and replaces fields.
    """

    list_display = ("name", "type", "behavior", "quantity_factor", "updated_at")
    list_filter = ("type", "behavior")
    search_fields = ("name", "ingredient__name")

    readonly_fields = ("updated_at", "created_at")

    fieldsets = (
        ("Basic Info", {
            "fields": ("name", "type", "ingredient", "behavior", "quantity_factor")
        }),
        ("Advanced Logic", {
            "fields": (
                ("target_selector", "replaces"),
                "expands_to",
            ),
            "description": (
                "<strong>target_selector</strong>: JSON filter for affected ingredients "
                "(e.g. {'by_type':['MILK'], 'by_name':['Bacon']}).<br>"
                "<strong>replaces</strong>: JSON map of replacements for REPLACE behavior "
                "(e.g. {'to': [['Oat Milk', 1.0]]}).<br>"
                "<strong>expands_to</strong>: Select ingredients this modifier adds."
            ),
        }),
        ("Cost & Pricing", {
            "fields": ("base_quantity", "unit", "cost_per_unit", "price_per_unit")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )

    # alias JSON fields with friendlier labels in the UI
    def formfield_for_dbfield(self, db_field, **kwargs):
        formfield = super().formfield_for_dbfield(db_field, **kwargs)
        if db_field.name == "target_selector":
            formfield.label = "Target Rules (JSON)"
            formfield.help_text = (
                "Defines which ingredients this modifier affects. "
                "Example: {'by_type':['MILK'], 'by_name':['Bacon']}"
            )
        elif db_field.name == "replaces":
            formfield.label = "Replacement Mapping (JSON)"
            formfield.help_text = (
                "Defines replacements for REPLACE behavior. "
                "Example: {'to': [['Oat Milk', 1.0]]}"
            )
        return formfield

    
