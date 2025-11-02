from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mscrInventory", "0021_recipemodifier_ingredient_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="SquareUnmappedItem",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
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
            ],
            options={
                "ordering": ("-last_seen", "item_name"),
                "unique_together": {("normalized_item", "normalized_price_point")},
            },
        ),
    ]
