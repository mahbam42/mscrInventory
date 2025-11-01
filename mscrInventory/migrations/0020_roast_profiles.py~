from django.db import migrations, models


def add_roast_type(apps, schema_editor):
    IngredientType = apps.get_model("mscrInventory", "IngredientType")
    IngredientType.objects.get_or_create(name="roasts")


def migrate_coffee_products(apps, schema_editor):
    connection = schema_editor.connection
    existing_tables = set(connection.introspection.table_names())
    if "mscrInventory_coffee" not in existing_tables:
        return

    IngredientType = apps.get_model("mscrInventory", "IngredientType")
    Ingredient = apps.get_model("mscrInventory", "Ingredient")
    RoastProfile = apps.get_model("mscrInventory", "RoastProfile")
    Product = apps.get_model("mscrInventory", "Product")

    roast_type = IngredientType.objects.filter(name__iexact="roasts").first()
    if roast_type is None:
        roast_type = IngredientType.objects.create(name="roasts")

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT product_ptr_id, bag_size, grind FROM mscrInventory_coffee"
        )
        rows = cursor.fetchall()

    for product_id, bag_size, grind in rows:
        product = Product.objects.filter(pk=product_id).first()
        if not product:
            continue

        ingredient = (
            Ingredient.objects.filter(name__iexact=product.name).first()
        )
        if ingredient is None:
            ingredient = Ingredient.objects.create(name=product.name, type=roast_type)
        else:
            if ingredient.type_id != roast_type.id:
                ingredient.type = roast_type
                ingredient.save(update_fields=["type"])

        RoastProfile.objects.update_or_create(
            ingredient_ptr=ingredient,
            defaults={
                "bag_size": bag_size or "11oz",
                "grind": grind or "whole",
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("mscrInventory", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RoastProfile",
            fields=[
                (
                    "ingredient_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=models.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="mscrInventory.ingredient",
                    ),
                ),
                (
                    "bag_size",
                    models.CharField(
                        choices=[
                            ("3oz", "3 oz sample"),
                            ("11oz", "11 oz bag"),
                            ("20oz", "20 oz bag"),
                            ("5lb", "5 lb bulk"),
                        ],
                        default="11oz",
                        max_length=10,
                    ),
                ),
                (
                    "grind",
                    models.CharField(
                        choices=[
                            ("whole", "Whole Bean"),
                            ("drip", "Drip Grind (flat bottom filter)"),
                            ("espresso", "Espresso Grind"),
                            ("coarse", "Coarse Grind (French Press)"),
                            ("fine", "Fine Grind (cone filter)"),
                        ],
                        default="whole",
                        max_length=10,
                    ),
                ),
            ],
            options={
                "verbose_name": "Roast Profile",
                "verbose_name_plural": "Roast Profiles",
            },
            bases=("mscrInventory.ingredient",),
        ),
        migrations.RunPython(add_roast_type, migrations.RunPython.noop),
        migrations.RunPython(migrate_coffee_products, migrations.RunPython.noop),
    ]
