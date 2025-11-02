from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("mscrInventory", "0021_recipemodifier_ingredient_type"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SquareUnmappedItem",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("source", models.CharField(choices=[("square", "Square")], default="square", max_length=32)),
                (
                    "item_type",
                    models.CharField(
                        choices=[
                            ("product", "Product"),
                            ("ingredient", "Ingredient"),
                            ("modifier", "Modifier"),
                        ],
                        default="product",
                        max_length=32,
                    ),
                ),
                ("item_name", models.CharField(max_length=255)),
                ("price_point_name", models.CharField(blank=True, max_length=255)),
                ("normalized_item", models.CharField(editable=False, max_length=255)),
                (
                    "normalized_price_point",
                    models.CharField(blank=True, editable=False, max_length=255),
                ),
                ("last_modifiers", models.JSONField(blank=True, default=list)),
                ("last_reason", models.CharField(blank=True, max_length=64)),
                ("seen_count", models.PositiveIntegerField(default=1)),
                ("first_seen", models.DateTimeField(auto_now_add=True)),
                ("last_seen", models.DateTimeField(auto_now=True)),
                ("resolved", models.BooleanField(default=False)),
                ("ignored", models.BooleanField(default=False)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "item_note",
                    models.CharField(
                        blank=True,
                        help_text="Optional note describing how to handle this unmapped item.",
                        max_length=255,
                    ),
                ),
                (
                    "linked_product",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="unmapped_square_links",
                        to="mscrInventory.product",
                    ),
                ),
                (
                    "linked_ingredient",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="unmapped_square_links",
                        to="mscrInventory.ingredient",
                    ),
                ),
                (
                    "linked_modifier",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="unmapped_square_links",
                        to="mscrInventory.recipemodifier",
                    ),
                ),
                (
                    "resolved_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="resolved_unmapped_items",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("-last_seen", "item_name"),
                "unique_together": {
                    ("source", "item_type", "normalized_item", "normalized_price_point")
                },
            },
        ),
    ]
