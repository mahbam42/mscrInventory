from django.conf import settings
from django.db import migrations, models
from django.db.utils import OperationalError, ProgrammingError
import django.db.models.deletion


class _SafeCreateSquareUnmappedItem(migrations.CreateModel):
    """Create the SquareUnmappedItem table only if it does not already exist."""

    def __init__(self, *args, table_name: str, **kwargs):
        self.table_name = table_name
        super().__init__(*args, **kwargs)

    def _table_exists(self, schema_editor) -> bool:
        with schema_editor.connection.cursor() as cursor:
            existing = schema_editor.connection.introspection.table_names(cursor)
        return self.table_name in existing

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        if self._table_exists(schema_editor):
            return

        try:
            super().database_forwards(app_label, schema_editor, from_state, to_state)
        except (OperationalError, ProgrammingError) as exc:  # pragma: no cover - defensive
            message = str(exc).lower()
            if "already exists" in message and self._table_exists(schema_editor):
                return
            raise

    def database_backwards(self, app_label, schema_editor, from_state, to_state):
        if not self._table_exists(schema_editor):
            return

        try:
            super().database_backwards(app_label, schema_editor, from_state, to_state)
        except (OperationalError, ProgrammingError):  # pragma: no cover - defensive
            if self._table_exists(schema_editor):
                raise


def _ensure_columns(apps, schema_editor):
    """Ensure newer columns exist on legacy tables created by early migrations."""

    model = apps.get_model("mscrInventory", "SquareUnmappedItem")
    table_name = model._meta.db_table

    with schema_editor.connection.cursor() as cursor:
        tables = schema_editor.connection.introspection.table_names(cursor)
        if table_name not in tables:
            return

        existing_columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor, table_name
            )
        }

    if "ignored" not in existing_columns:
        field = models.BooleanField(default=False)
        field.set_attributes_from_name("ignored")
        schema_editor.add_field(model, field, preserve_default=False)


class Migration(migrations.Migration):

    dependencies = [
        ("mscrInventory", "0021_recipemodifier_ingredient_type"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        _SafeCreateSquareUnmappedItem(
            name="SquareUnmappedItem",
            table_name="mscrInventory_squareunmappeditem",
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
                (
                    "source",
                    models.CharField(
                        choices=[("square", "Square")],
                        default="square",
                        max_length=32,
                    ),
                ),
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
                (
                    "normalized_item",
                    models.CharField(editable=False, max_length=255),
                ),
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
        migrations.RunPython(_ensure_columns, migrations.RunPython.noop),
    ]
