from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("mscrInventory", "0022_squareunmappeditems"),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, migrations.RunPython.noop),
    ]
