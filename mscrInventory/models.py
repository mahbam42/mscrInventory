# inventory/models.py

import re
from decimal import Decimal
from typing import Optional
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import connection, models, transaction, IntegrityError
from django.utils import timezone


# Helpers
PLATFORM_CHOICES = (
    ("shopify", "Shopify"),
    ("square", "Square"),
)

STOCKENTRY_SOURCE_CHOICES = (
    ("purchase", "Purchase"),
    ("adjustment", "Adjustment"),
    ("correction", "Correction"),
)

USAGE_SOURCE_CHOICES = (
    ("shopify", "Shopify"),
    ("square", "Square"),
    ("manual", "Manual"),
)


class Product(models.Model):
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=128, unique=True)
    shopify_id = models.CharField(max_length=128, null=True, blank=True)
    square_id = models.CharField(max_length=128, null=True, blank=True)
    
    # ✅ Added this
    TEMPERATURE_CHOICES = [
        ("hot", "Hot"),
        ("cold", "Cold"),
        ("na", "N/A"),
    ]
    temperature_type = models.CharField(
        max_length=10,
        choices=TEMPERATURE_CHOICES,
        default="na",
    )
    categories = models.ManyToManyField("Category", related_name="products", blank=True)
    # category = models.CharField(max_length=128, blank=True)
    modifiers = models.ManyToManyField("RecipeModifier", blank=True, related_name="products")
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["sku"]),
            models.Index(fields=["shopify_id"]),
            models.Index(fields=["square_id"]),
        ]

    @property
    def calculated_cogs(self):
        """
        Returns total cost of goods sold for this product,
        based on linked ingredients and their average cost.
        """
        total = Decimal("0")
        for item in self.recipe_items.select_related("ingredient"):
            if not item.ingredient:
                continue
            qty = item.quantity or Decimal("0")
            cost = item.ingredient.average_cost_per_unit or Decimal("0")
            total += qty * cost
        return total.quantize(Decimal("0.0001"))

    def __str__(self):
        return f"{self.name} ({self.sku})"

class ProductVariantCache(models.Model):
    """
    Cache of product variants derived from order imports (Square, Shopify, etc.).
    Used to track descriptive modifiers like size, temperature, or packaging.
    """
    product = models.ForeignKey("Product", on_delete=models.CASCADE, related_name="variant_cache")
    platform = models.CharField(max_length=32, default="square")
    variant_name = models.CharField(max_length=255, help_text="Normalized variant descriptor (e.g., 'iced small')")
    data = models.JSONField(default=dict, blank=True, help_text="Additional normalized details (e.g. {'temp': 'iced'})")
    last_seen = models.DateTimeField(auto_now=True)
    usage_count = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ("product", "platform", "variant_name")

    def __str__(self):
        return f"{self.product.name} — {self.variant_name}"
    
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class IngredientType(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name
    
class UnitType(models.Model):
    name = models.CharField(max_length=50, unique=True)
    abbreviation = models.CharField(max_length=10, blank=True)
    conversion_to_base = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal("1.0000"))

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.abbreviation or self.name

class Ingredient(models.Model):
    name = models.CharField(max_length=255, unique=True)
    type = models.ForeignKey(IngredientType, on_delete=models.SET_NULL, null=True, blank=True)
    unit_type = models.ForeignKey(UnitType, on_delete=models.SET_NULL, null=True, blank=True)
    current_stock = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))
    case_size = models.PositiveIntegerField(null=True, blank=True, help_text="Units per case, if applicable.")
    reorder_point = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))
    lead_time = models.PositiveIntegerField(null=True, blank=True, help_text="Lead time in days")
    average_cost_per_unit = models.DecimalField(max_digits=12, decimal_places=6, default=Decimal("0.000000"))
    last_updated = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def increment_stock(self, quantity: Decimal, cost_per_unit: Decimal):
        """
        Increase stock and recalculate weighted average cost.
        Called by StockEntry.save() inside a transaction.
        """
        if quantity <= 0:
            return

        old_stock = Decimal(self.current_stock or 0)
        old_cost = Decimal(self.average_cost_per_unit or 0)
        new_stock = Decimal(quantity)
        new_cost = Decimal(cost_per_unit)

        total_qty = old_stock + new_stock
        if total_qty > 0:
            weighted_avg = ((old_stock * old_cost) + (new_stock * new_cost)) / total_qty
        else:
            weighted_avg = new_cost

        self.average_cost_per_unit = weighted_avg.quantize(Decimal("0.000001"))
        self.current_stock = total_qty.quantize(Decimal("0.000"))
        self.save(update_fields=["average_cost_per_unit", "current_stock", "last_updated"])

    def decrement_stock(self, quantity: Decimal):
        """
        Decrease stock by quantity. Does NOT recalculate cost.
        Should be called in transaction when logging usage.
        """
        new_stock = (Decimal(self.current_stock or 0) - Decimal(quantity))
        # Allow negatives (so we can see overuse), but you might want to block it.
        self.current_stock = new_stock.quantize(Decimal("0.000"))
        self.save(update_fields=["current_stock", "last_updated"])


class RoastProfile(Ingredient):
    """Retail coffee bag metadata tied to a roast ingredient."""

    BAG_SIZES = [
        ("3oz", "3 oz sample"),
        ("11oz", "11 oz bag"),
        ("20oz", "20 oz bag"),
        ("5lb", "5 lb bulk"),
    ]

    GRINDS = [
        ("whole", "Whole Bean"),
        ("drip", "Drip Grind (flat bottom filter)"),
        ("espresso", "Espresso Grind"),
        ("coarse", "Coarse Grind (French Press)"),
        ("fine", "Fine Grind (cone filter)"),
    ]

    bag_size = models.CharField(max_length=10, choices=BAG_SIZES, default="11oz")
    grind = models.CharField(max_length=10, choices=GRINDS, default="whole")

    class Meta:
        verbose_name = "Roast Profile"
        verbose_name_plural = "Roast Profiles"


class StockEntry(models.Model):
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name="stock_entries")
    quantity_added = models.DecimalField(max_digits=12, decimal_places=3)
    cost_per_unit = models.DecimalField(max_digits=12, decimal_places=6)
    date_received = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=32, choices=STOCKENTRY_SOURCE_CHOICES, default="purchase")
    note = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-date_received"]

    def __str__(self):
        return f"{self.ingredient.name} +{self.quantity_added} @ {self.cost_per_unit}"

    def save(self, *args, **kwargs):
        """
        On save, update ingredient's stock and weighted average cost.
        If this is an update (existing pk), behavior is naive: we handle only create.
        For production, handle edits/deletes explicitly (reverse previous effect).
        """
        is_create = self.pk is None
        with transaction.atomic():
            super().save(*args, **kwargs)
            if is_create and self.quantity_added and self.cost_per_unit is not None:
                # Update Ingredient aggregate fields
                self.ingredient.increment_stock(self.quantity_added, self.cost_per_unit)
    
class RecipeItem(models.Model):
    """
    Represents a single ingredient entry within a product's recipe.

    Each RecipeItem links one Product to one Ingredient, with a specific
    quantity, unit, and optional cost/price data. Together, all RecipeItems
    for a Product define that product's complete recipe and cost-of-goods basis.

    Example:
        Latte  →  [ (Espresso Shot, 1 unit), (Milk, 8 oz), (Foam, 1 unit) ]
    """
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="recipe_items",
        null=False,
        blank=False,
    )
    ingredient = models.ForeignKey(
        Ingredient,
        on_delete=models.CASCADE,
        related_name="recipe_items",
        null=False,
        blank=False,
    )
    quantity = models.DecimalField(max_digits=6, decimal_places=2, null=False, blank=False)
    unit = models.CharField(max_length=32, null=False, blank=False, default="unit")
    cost_per_unit = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    price_per_unit = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(product__isnull=True),
                name="recipeitem_product_required"
            ),
            models.CheckConstraint(
                condition=~models.Q(ingredient__isnull=True),
                name="recipeitem_ingredient_required"
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=0),
                name="recipeitem_quantity_nonnegative"
            ),
            models.UniqueConstraint(
                fields=["product", "ingredient"],
                name="unique_ingredient_per_recipe"
            ),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.quantity}{self.unit} {self.ingredient.name}"


class ModifierBehavior(models.TextChoices):
    ADD = "add", "Add"
    REPLACE = "replace", "Replace"
    SCALE = "scale", "Scale"

class RecipeModifier(models.Model):
    """
    Modifiers are extensions of Ingredients (e.g. milk options, syrups, extra shots).
    Each links to a base Ingredient but may have its own cost, price, and behavior.

    Extended behavior system:
        - behavior: ADD, REPLACE, SCALE
        - quantity_factor: scaling multiplier (replaces size_multiplier)
        - target_selector: defines which ingredients to target (by type/name)
        - replaces: specifies replacements for REPLACE behavior
    """

    class ModifierBehavior(models.TextChoices):
        ADD = "add", "Add"
        REPLACE = "replace", "Replace"
        SCALE = "scale", "Scale"
        EXPAND = "expand", "Expand" # not used yet

    name = models.CharField(max_length=100, unique=True)
    ingredient_type = models.ForeignKey(
        IngredientType,
        on_delete=models.PROTECT,
        related_name="recipe_modifiers",
    )

    # ⚙️ The new unified behavior system
    behavior = models.CharField(
        max_length=10,
        choices=ModifierBehavior.choices,
        default=ModifierBehavior.ADD,
    )

    quantity_factor = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("1.0"),
        help_text="Multiplier applied to matching ingredients. Replaces size_multiplier."
    )

    target_selector = models.JSONField(
        blank=True,
        null=True,
        help_text=(
            "Filter for which ingredients this modifier affects, e.g. "
            '{"by_type":[1,2],"by_name":["Bacon"]}'
        ),
    )

    replaces = models.JSONField(
        blank=True,
        null=True,
        help_text=(
            "Mapping of replacements for REPLACE behavior, e.g. "
            '{"to":[["Oat Milk",1.0]]}'
        ),
    )

    # The ingredient this modifier extends (e.g. 'Oat Milk' extends 'Milk')
    ingredient = models.ForeignKey("Ingredient", on_delete=models.CASCADE)

    # Default amount used when this modifier is applied
    base_quantity = models.DecimalField(max_digits=8, decimal_places=2)

    # Unit of measure (e.g. 'oz', 'g')
    unit = models.CharField(max_length=20)

    # ⚠️ Legacy field (deprecated)
    size_multiplier = models.BooleanField(default=True)

    # Optional override for cost and price calculations
    cost_per_unit = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    price_per_unit = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))

    expands_to = models.ManyToManyField(
        "self",
        blank=True,
        symmetrical=False,
        help_text=(
            "For special modifiers that expand into multiple others. "
            "E.g., 'Dirty Chai' expands to [Espresso Shot, Chai Concentrate]."
        ),
    )
    # logging fields
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["ingredient_type__name", "name"]

    def __str__(self):
        ingredient_type = getattr(self.ingredient_type, "name", "Uncategorized")
        return f"{self.name} ({ingredient_type})"


class Order(models.Model):
    order_id = models.CharField(max_length=255, help_text="Platform-specific order id")
    platform = models.CharField(max_length=32, choices=PLATFORM_CHOICES)
    order_date = models.DateTimeField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    data_raw = models.JSONField(null=True, blank=True)
    synced_at = models.DateTimeField(default=timezone.now)

    class Meta:
        unique_together = ("order_id", "platform")
        ordering = ["-order_date"]

    def __str__(self):
        return f"{self.platform} #{self.order_id} - {self.order_date.date()}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    variant_info = models.JSONField(default=dict, blank=True) # e.g., size, temp

    def __str__(self):
        prod = self.product.sku if self.product else "Unmapped"
        return f"{prod} x{self.quantity}"

class IngredientUsageLog(models.Model):
    """
    Log of ingredient usage per date. Typically created by the sync process that
    consumes OrderItems+RecipeItems and aggregates by ingredient.
    """
    ingredient = models.ForeignKey(Ingredient, on_delete=models.CASCADE, related_name="usage_logs")
    date = models.DateField()  # usage date (e.g., the cafe day)
    quantity_used = models.DecimalField(max_digits=12, decimal_places=3)
    source = models.CharField(max_length=32, choices=USAGE_SOURCE_CHOICES, default="manual")
    calculated_from_orders = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    note = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ("ingredient", "date", "source")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.ingredient.name} used {self.quantity_used} on {self.date}"

    def save(self, *args, **kwargs):
        """
        On create, decrement ingredient.current_stock.
        If updating an existing record, compute delta and apply difference.
        """
        with transaction.atomic():
            if self.pk:
                # existing; compute delta
                old = IngredientUsageLog.objects.select_for_update().get(pk=self.pk)
                delta = Decimal(self.quantity_used) - Decimal(old.quantity_used)
                super().save(*args, **kwargs)
                if delta != 0:
                    # positive delta => additional consumption
                    self.ingredient.decrement_stock(delta)
            else:
                super().save(*args, **kwargs)
                # new usage -> decrement the stock by the full amount
                self.ingredient.decrement_stock(Decimal(self.quantity_used))


class ImportLog(models.Model):
    SOURCE_CHOICES = [
        ("square", "Square"),
        ("shopify", "Shopify"),
    ]
    RUN_TYPE_CHOICES = [
        ("dry-run", "Dry Run"),
        ("live", "Live"),
    ]

    source = models.CharField(max_length=50, choices=SOURCE_CHOICES)
    run_type = models.CharField(max_length=20, choices=RUN_TYPE_CHOICES, default="dry-run")
    filename = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    rows_processed = models.PositiveIntegerField(default=0)
    matched_count = models.PositiveIntegerField(default=0)
    unmatched_count = models.PositiveIntegerField(default=0)
    order_items = models.PositiveIntegerField(default=0)
    modifiers_applied = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    summary = models.TextField(blank=True)
    log_output = models.TextField(blank=True, null=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="import_logs",
    )

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        timestamp = self.created_at.astimezone(timezone.get_current_timezone()) if self.created_at else None
        ts_display = timestamp.strftime("%Y-%m-%d %H:%M") if timestamp else "pending"
        return f"{self.get_source_display()} {self.get_run_type_display()} @ {ts_display}"


class SquareUnmappedItem(models.Model):
    """Tracks Square rows that could not be resolved to an internal mapping."""

    SOURCE_CHOICES = [("square", "Square")]
    ITEM_TYPE_CHOICES = [
        ("product", "Product"),
        ("ingredient", "Ingredient"),
        ("modifier", "Modifier"),
    ]

    source = models.CharField(max_length=32, choices=SOURCE_CHOICES, default="square")
    item_type = models.CharField(max_length=32, choices=ITEM_TYPE_CHOICES, default="product")
    item_name = models.CharField(max_length=255)
    price_point_name = models.CharField(max_length=255, blank=True)
    normalized_item = models.CharField(max_length=255, editable=False)
    normalized_price_point = models.CharField(max_length=255, editable=False, blank=True)
    last_modifiers = models.JSONField(default=list, blank=True)
    last_reason = models.CharField(max_length=64, blank=True)
    seen_count = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    resolved = models.BooleanField(default=False)
    ignored = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_unmapped_items",
    )
    item_note = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional note describing how to handle this unmapped item.",
    )
    linked_product = models.ForeignKey(
        "Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unmapped_square_links",
    )
    linked_ingredient = models.ForeignKey(
        "Ingredient",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unmapped_square_links",
    )
    linked_modifier = models.ForeignKey(
        "RecipeModifier",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unmapped_square_links",
    )

    class Meta:
        unique_together = (
            "source",
            "item_type",
            "normalized_item",
            "normalized_price_point",
        )
        ordering = ("-last_seen", "item_name")

    def __str__(self):
        return self.display_label

    @staticmethod
    def _normalize_value(value) -> str:
        raw = (value or "").strip().lower()
        cleaned = re.sub(r"[^a-z0-9\s]", " ", raw)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @property
    def display_label(self) -> str:
        if self.price_point_name:
            return f"{self.item_name} — {self.price_point_name}"
        return self.item_name

    @property
    def is_resolved(self) -> bool:
        return self.resolved or self.ignored

    def mark_resolved(
        self,
        *,
        user=None,
        ignored: bool = False,
        product: Optional["Product"] = None,
        ingredient: Optional["Ingredient"] = None,
        modifier: Optional["RecipeModifier"] = None,
        note: str | None = None,
    ) -> None:
        """Mark the item as resolved and optionally link an existing record."""

        update_fields = {"resolved", "ignored", "resolved_at"}

        self.resolved = not ignored
        self.ignored = ignored
        self.resolved_at = timezone.now()
        self.resolved_by = user
        update_fields.add("resolved_by")

        if self.item_type == "product":
            self.linked_product = product
        else:
            self.linked_product = None
        update_fields.add("linked_product")

        if self.item_type == "ingredient":
            self.linked_ingredient = ingredient
        else:
            self.linked_ingredient = None
        update_fields.add("linked_ingredient")

        if self.item_type == "modifier":
            self.linked_modifier = modifier
        else:
            self.linked_modifier = None
        update_fields.add("linked_modifier")

        if note is not None:
            self.item_note = note
            update_fields.add("item_note")

        self.save(update_fields=list(update_fields))

    def reopen(self) -> None:
        """Reopen an item for review."""

        self.resolved = False
        self.ignored = False
        self.resolved_at = None
        self.resolved_by = None
        self.linked_product = None
        self.linked_ingredient = None
        self.linked_modifier = None
        self.save(
            update_fields=[
                "resolved",
                "ignored",
                "resolved_at",
                "resolved_by",
                "linked_product",
                "linked_ingredient",
                "linked_modifier",
            ]
        )

    def save(self, *args, **kwargs):
        self.normalized_item = self._normalize_value(self.item_name)
        self.normalized_price_point = self._normalize_value(self.price_point_name)
        super().save(*args, **kwargs)


class SquareUnmappedItem(models.Model):
    """Tracks Square rows that could not be resolved to an internal mapping."""

    SOURCE_CHOICES = [("square", "Square")]
    ITEM_TYPE_CHOICES = [
        ("product", "Product"),
        ("ingredient", "Ingredient"),
        ("modifier", "Modifier"),
    ]

    source = models.CharField(max_length=32, choices=SOURCE_CHOICES, default="square")
    item_type = models.CharField(max_length=32, choices=ITEM_TYPE_CHOICES, default="product")
    item_name = models.CharField(max_length=255)
    price_point_name = models.CharField(max_length=255, blank=True)
    normalized_item = models.CharField(max_length=255, editable=False)
    normalized_price_point = models.CharField(max_length=255, editable=False, blank=True)
    last_modifiers = models.JSONField(default=list, blank=True)
    last_reason = models.CharField(max_length=64, blank=True)
    seen_count = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    resolved = models.BooleanField(default=False)
    ignored = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_unmapped_items",
    )
    item_note = models.CharField(
        max_length=255,
        blank=True,
        help_text="Optional note describing how to handle this unmapped item.",
    )
    linked_product = models.ForeignKey(
        "Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unmapped_square_links",
    )
    linked_ingredient = models.ForeignKey(
        "Ingredient",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unmapped_square_links",
    )
    linked_modifier = models.ForeignKey(
        "RecipeModifier",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unmapped_square_links",
    )

    class Meta:
        unique_together = (
            "source",
            "item_type",
            "normalized_item",
            "normalized_price_point",
        )
        ordering = ("-last_seen", "item_name")

    def __str__(self):
        return self.display_label

    @staticmethod
    def _normalize_value(value) -> str:
        raw = (value or "").strip().lower()
        cleaned = re.sub(r"[^a-z0-9\s]", " ", raw)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    @property
    def display_label(self) -> str:
        if self.price_point_name:
            return f"{self.item_name} — {self.price_point_name}"
        return self.item_name

    @property
    def is_resolved(self) -> bool:
        return self.resolved or self.ignored

    def mark_resolved(
        self,
        *,
        user=None,
        ignored: bool = False,
        product: Optional["Product"] = None,
        ingredient: Optional["Ingredient"] = None,
        modifier: Optional["RecipeModifier"] = None,
        note: str | None = None,
    ) -> None:
        """Mark the item as resolved and optionally link an existing record."""

        update_fields = {"resolved", "ignored", "resolved_at"}

        self.resolved = not ignored
        self.ignored = ignored
        self.resolved_at = timezone.now()
        self.resolved_by = user
        update_fields.add("resolved_by")

        if self.item_type == "product":
            self.linked_product = product
        else:
            self.linked_product = None
        update_fields.add("linked_product")

        if self.item_type == "ingredient":
            self.linked_ingredient = ingredient
        else:
            self.linked_ingredient = None
        update_fields.add("linked_ingredient")

        if self.item_type == "modifier":
            self.linked_modifier = modifier
        else:
            self.linked_modifier = None
        update_fields.add("linked_modifier")

        if note is not None:
            self.item_note = note
            update_fields.add("item_note")

        self.save(update_fields=list(update_fields))

    def reopen(self) -> None:
        """Reopen an item for review."""

        self.resolved = False
        self.ignored = False
        self.resolved_at = None
        self.resolved_by = None
        self.linked_product = None
        self.linked_ingredient = None
        self.linked_modifier = None
        self.save(
            update_fields=[
                "resolved",
                "ignored",
                "resolved_at",
                "resolved_by",
                "linked_product",
                "linked_ingredient",
                "linked_modifier",
            ]
        )

    def save(self, *args, **kwargs):
        self.normalized_item = self._normalize_value(self.item_name)
        self.normalized_price_point = self._normalize_value(self.price_point_name)
        super().save(*args, **kwargs)


def get_or_create_roast_profile(ingredient: "Ingredient") -> RoastProfile | None:
    """Return the roast profile for an ingredient, creating it if needed."""

    if ingredient is None:
        return None

    if ingredient.pk is None:
        return None

    try:
        return ingredient.roastprofile
    except RoastProfile.DoesNotExist:
        pass

    defaults = {
        "bag_size": RoastProfile._meta.get_field("bag_size").get_default(),
        "grind": RoastProfile._meta.get_field("grind").get_default(),
    }

    table_name = connection.ops.quote_name(RoastProfile._meta.db_table)
    parent_column = connection.ops.quote_name(
        RoastProfile._meta.get_field("ingredient_ptr").column
    )
    bag_column = connection.ops.quote_name(RoastProfile._meta.get_field("bag_size").column)
    grind_column = connection.ops.quote_name(RoastProfile._meta.get_field("grind").column)

    with transaction.atomic():
        with connection.cursor() as cursor:
            try:
                cursor.execute(
                    f"INSERT INTO {table_name} ({parent_column}, {bag_column}, {grind_column}) "
                    "VALUES (%s, %s, %s)",
                    [ingredient.pk, defaults["bag_size"], defaults["grind"]],
                )
            except IntegrityError:
                # Another transaction created the profile first; fetch below.
                pass

    try:
        return RoastProfile.objects.get(pk=ingredient.pk)
    except RoastProfile.DoesNotExist:
        return None


@receiver(post_save, sender=Ingredient)
def ensure_roast_profile(sender, instance, created, **kwargs):
    """Ensure roast ingredients always have an attached RoastProfile."""

    roast_type = IngredientType.objects.filter(name__iexact="roasts").first()
    has_roast_type = bool(roast_type and instance.type_id == roast_type.id)
    try:
        profile = instance.roastprofile
    except RoastProfile.DoesNotExist:
        profile = None

    if has_roast_type and profile is None:
        get_or_create_roast_profile(instance)
    elif not has_roast_type and profile is not None:
        profile.delete()
