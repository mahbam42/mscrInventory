from django.db import migrations, models

def seed_initial_types(apps, schema_editor):
    """Create UnitType and IngredientType base rows."""
    UnitType = apps.get_model("mscrInventory", "UnitType")
    IngredientType = apps.get_model("mscrInventory", "IngredientType")

    units = [
        ("Fluid Ounce", "fl_oz", 1),
        ("Ounce", "oz", 1),
        ("Pound", "lb", 16),
        ("Gram", "g", 0.03527),
        ("Kilogram", "kg", 35.274),
        ("Liter", "L", 33.814),
        ("Milliliter", "ml", 0.033814),
        ("Unit", "unit", 1),
    ]
    for n, a, c in units:
        UnitType.objects.get_or_create(name=n, abbreviation=a, conversion_to_base=c)

    types = [
        "MILK", "FLAVOR", "SYRUP", "SUGAR", "EXTRA", "COFFEE",
        "PACKAGING", "MISC", "BAGEL", "SPREAD", "TOPPING",
        "TOAST", "BAKED_GOOD", "MUFFIN", "COOKIE",
    ]
    for t in types:
        IngredientType.objects.get_or_create(name=t)

def backfill_ingredient_fks(apps, schema_editor):
    """Now that Ingredient.unit_type and type are FKs, map existing strings to objects."""
    Ingredient = apps.get_model("mscrInventory", "Ingredient")
    UnitType = apps.get_model("mscrInventory", "UnitType")
    IngredientType = apps.get_model("mscrInventory", "IngredientType")

    # Build lookup maps
    unit_map = {u.abbreviation.lower(): u for u in UnitType.objects.all()}
    type_map = {t.name.upper(): t for t in IngredientType.objects.all()}

    for ing in Ingredient.objects.all():
        # old CharFields are now text values (not objects)
        unit_val = getattr(ing, "unit_type", None)
        type_val = getattr(ing, "type", None)

        # Try to match abbreviations and type names
        if isinstance(unit_val, str):
            ing.unit_type = unit_map.get(unit_val.lower()) or unit_map.get("unit")
        if isinstance(type_val, str):
            ing.type = type_map.get(type_val.upper()) or type_map.get("MISC")

        ing.save()

def unseed_initial_data(apps, schema_editor):
    apps.get_model("mscrInventory", "UnitType").objects.all().delete()
    apps.get_model("mscrInventory", "IngredientType").objects.all().delete()


class Migration(migrations.Migration):
    atomic = False  # important for multi-step migration

    dependencies = [
        ("mscrInventory", "0008_alter_recipeitem_unique_together_and_more"),
    ]

    operations = [
        # 1️⃣ Create lookup tables
        migrations.CreateModel(
            name="UnitType",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=50, unique=True)),
                ("abbreviation", models.CharField(max_length=10, unique=True)),
                ("conversion_to_base", models.FloatField(default=1.0)),
            ],
        ),
        migrations.CreateModel(
            name="IngredientType",
            fields=[
                ("id", models.AutoField(primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=50, unique=True)),
            ],
        ),

        # 2️⃣ Seed them
        migrations.RunPython(seed_initial_types, unseed_initial_data),

        # 3️⃣ Alter Ingredient fields to FK
        migrations.AlterField(
            model_name="ingredient",
            name="unit_type",
            field=models.ForeignKey(
                to="mscrInventory.UnitType",
                null=True,
                blank=True,
                on_delete=models.SET_NULL,
            ),
        ),
        migrations.AlterField(
            model_name="ingredient",
            name="type",
            field=models.ForeignKey(
                to="mscrInventory.IngredientType",
                null=True,
                blank=True,
                on_delete=models.SET_NULL,
            ),
        ),

        # 4️⃣ Now backfill the ingredients safely
        migrations.RunPython(backfill_ingredient_fks, reverse_code=migrations.RunPython.noop),
    ]

