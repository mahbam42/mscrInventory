from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mscrInventory", "0023_squareunmappeditem"),
    ]

    operations = [
        migrations.RenameField(
            model_name="importlog",
            old_name="last_run",
            new_name="created_at",
        ),
        migrations.RenameField(
            model_name="importlog",
            old_name="log_excerpt",
            new_name="log_output",
        ),
        migrations.AlterField(
            model_name="importlog",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="importlog",
            name="source",
            field=models.CharField(choices=[("square", "Square"), ("shopify", "Shopify")], max_length=50),
        ),
        migrations.AddField(
            model_name="importlog",
            name="duration_seconds",
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
        migrations.AddField(
            model_name="importlog",
            name="error_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="importlog",
            name="filename",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="importlog",
            name="finished_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="importlog",
            name="matched_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="importlog",
            name="modifiers_applied",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="importlog",
            name="order_items",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="importlog",
            name="rows_processed",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="importlog",
            name="run_type",
            field=models.CharField(choices=[("dry-run", "Dry Run"), ("live", "Live")], default="dry-run", max_length=20),
        ),
        migrations.AddField(
            model_name="importlog",
            name="started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="importlog",
            name="summary",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="importlog",
            name="unmatched_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="importlog",
            name="uploaded_by",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, related_name="import_logs", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name="importlog",
            name="log_output",
            field=models.TextField(blank=True, null=True),
        ),
        migrations.AlterModelOptions(
            name="importlog",
            options={"ordering": ("-created_at",)},
        ),
    ]
