from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mscrInventory", "0033_packaging_expands_to_reset"),
    ]

    operations = [
        migrations.AddField(
            model_name="squareunmappeditem",
            name="last_raw_row",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]

