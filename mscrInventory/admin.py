# admin.py (top of file)
import io
import csv
import datetime
import zipfile
from decimal import Decimal
from django.http import HttpResponse
from django.contrib import admin
from django import forms
from django.forms.models import inlineformset_factory


from .models import (
    Product,
    Ingredient,
    RecipeItem,
    RecipeModifier,
    RecipeModifierAlias,
    Category,
    Order,
    OrderItem,
    IngredientUsageLog,
    StockEntry,
    ImportLog,
    IngredientType,
    UnitType,
    RoastProfile,
    get_or_create_roast_profile,
    SquareUnmappedItem,
    ContainerType, 
    Packaging, 
    PackagingSizeScale
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

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "category_list", "active", "created_at")
    list_filter = ("active", "categories")

    search_fields = ('name', 'sku')
    filter_horizontal = ("modifiers",)  # 👈 adds nice M2M selector widget
    inlines = [RecipeItemInline]   # 👈 use the inline class defined above
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


class RoastProfileInline(admin.StackedInline):
    model = RoastProfile
    extra = 0
    can_delete = False
    verbose_name_plural = "Roast Properties"
    fields = ["bag_size", "grind"]

# --- SizeScale Inline Formset ---
PackagingSizeScaleFormSet = inlineformset_factory(
    Packaging,
    PackagingSizeScale,
    fields=("temperature", "size_label", "multiplier"),
    extra=1,
    can_delete=True
)


# --- Packaging Inline (for Ingredient) ---
class PackagingInlineForm(forms.ModelForm):
    class Meta:
        model = Packaging
        fields = ("temp", "container")

class PackagingInline(admin.StackedInline):
    model = Packaging
    form = PackagingInlineForm
    extra = 1
    autocomplete_fields = ("container",)
    verbose_name_plural = "Packaging Options"

    # Attach the scale formset
    def get_inline_formsets(self, request, formsets, inline_instances, obj=None):
        formsets = super().get_inline_formsets(request, formsets, inline_instances, obj)
        if obj:
            # create the nested scale formset
            for inline_formset in formsets:
                if isinstance(inline_formset.model, Packaging):
                    inline_formset.size_scale_formset = PackagingSizeScaleFormSet(
                        instance=inline_formset.instance, data=request.POST or None
                    )
        return formsets

# --- Admin for ContainerType ---
@admin.register(ContainerType)
class ContainerTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "capacity", "unit_type", "description")
    search_fields = ("name", "description")
    list_filter = ("unit_type",)
    ordering = ("name",)

@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = (
        "name", "type", "unit_type", "current_stock", "average_cost_per_unit",
        "reorder_point", "lead_time", "last_updated"
    )
    list_filter = ("type", "unit_type",)
    search_fields = ("name",)
    inlines = [StockEntryInline, PackagingInline]

    def get_inline_instances(self, request, obj=None):
        inline_instances = super().get_inline_instances(request, obj)
        if not obj:
            return inline_instances

        # --- Add Roast inline if ingredient type is a coffee roast
        roast_type = IngredientType.objects.filter(name__iexact="roasts").first()
        is_roast = bool(roast_type and obj.type_id == roast_type.id)
        try:
            profile = obj.roastprofile
        except RoastProfile.DoesNotExist:
            profile = None

        if is_roast:
            profile = profile or get_or_create_roast_profile(obj)
            if profile is not None:
                inline_instances.insert(0, RoastProfileInline(self.model, self.admin_site))

        # --- Add Packaging inline if ingredient type is packaging-related
        packaging_type = IngredientType.objects.filter(name__iexact="packaging").first()
        is_packaging = bool(packaging_type and obj.type_id == packaging_type.id)
        if is_packaging:
            inline_instances.append(PackagingInline(self.model, self.admin_site))

        return inline_instances
    


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


@admin.register(ImportLog)
class ImportLogAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "run_type",
        "filename",
        "created_at",
        "rows_processed",
        "unmatched_count",
        "short_summary",
    )
    list_filter = ("source", "run_type")
    search_fields = ("filename", "summary", "log_output")
    readonly_fields = (
        "source",
        "run_type",
        "filename",
        "created_at",
        "started_at",
        "finished_at",
        "duration_seconds",
        "rows_processed",
        "matched_count",
        "unmatched_count",
        "order_items",
        "modifiers_applied",
        "error_count",
        "summary",
        "log_output",
        "uploaded_by",
    )
    ordering = ("-created_at",)

    def short_summary(self, obj):
        if not obj.summary:
            return "—"
        preview = obj.summary.strip().splitlines()[0]
        return (preview[:75] + "…") if len(preview) > 75 else preview

    short_summary.short_description = "Summary"


@admin.register(IngredientUsageLog)
class IngredientUsageLogAdmin(admin.ModelAdmin):
    list_display = ("ingredient", "date", "quantity_used", "source", "calculated_from_orders")
    list_filter = ("source", "calculated_from_orders")
    search_fields = ("ingredient__name", "note")
    ordering = ("-date", "ingredient__name")


@admin.register(SquareUnmappedItem)
class SquareUnmappedItemAdmin(admin.ModelAdmin):
    list_display = (
        "display_label",
        "source",
        "item_type",
        "seen_count",
        "resolved",
        "ignored",
        "last_seen",
    )
    list_filter = ("source", "item_type", "resolved", "ignored")
    search_fields = ("item_name", "price_point_name", "last_reason")
    readonly_fields = (
        "normalized_item",
        "normalized_price_point",
        "first_seen",
        "last_seen",
        "seen_count",
    )
    ordering = ("-last_seen",)
    autocomplete_fields = ("linked_product", "linked_ingredient", "linked_modifier")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    ("source", "item_type"),
                    "item_name",
                    "price_point_name",
                    "last_reason",
                    "item_note",
                )
            },
        ),
        (
            "Resolution",
            {
                "fields": (
                    ("resolved", "ignored"),
                    ("linked_product", "linked_ingredient", "linked_modifier"),
                    ("resolved_by", "resolved_at"),
                )
            },
        ),
        (
            "History",
            {
                "fields": (
                    "seen_count",
                    ("first_seen", "last_seen"),
                    "last_modifiers",
                    ("normalized_item", "normalized_price_point"),
                )
            },
        ),
    )

    actions = ["mark_as_resolved", "mark_as_ignored", "reopen_items"]

    @admin.action(description="Mark selected items as resolved")
    def mark_as_resolved(self, request, queryset):
        for item in queryset:
            item.mark_resolved(user=request.user)

    @admin.action(description="Ignore selected items")
    def mark_as_ignored(self, request, queryset):
        for item in queryset:
            item.mark_resolved(user=request.user, ignored=True)

    @admin.action(description="Reopen selected items")
    def reopen_items(self, request, queryset):
        for item in queryset:
            item.reopen()



class RecipeModifierAliasInline(admin.TabularInline):
    model = RecipeModifierAlias
    extra = 1
    fields = ("raw_label", "normalized_label")
    readonly_fields = ("normalized_label",)

@admin.register(RecipeModifier)
class RecipeModifierAdmin(admin.ModelAdmin):
    """
    Admin interface for RecipeModifier, supporting new DB-driven behavior logic.
    Includes JSON editing for target_selector and replaces fields.
    """

    list_display = ("name", "ingredient_type", "behavior", "quantity_factor", "updated_at")
    list_filter = ("ingredient_type", "behavior")
    search_fields = ("name", "ingredient__name")

    readonly_fields = ("updated_at", "created_at")

    inlines = [RecipeModifierAliasInline]

    fieldsets = (
        ("Basic Info", {
            "fields": ("name", "ingredient_type", "ingredient", "behavior", "quantity_factor")
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

    
