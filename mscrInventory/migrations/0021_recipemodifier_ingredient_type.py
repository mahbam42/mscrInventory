from django.db import migrations, models

MODIFIER_TYPE_CHOICES = {
    "MILK": "Milk",
    "FLAVOR": "Flavor Shot",
    "SYRUP": "Syrup",
    "SUGAR": "Sugar",
    "EXTRA": "Extra",
    "BAGEL": "Bagel",
    "SPREAD": "Spread",
    "TOPPING": "Topping",
    "TOAST": "Toast",
    "MUFFIN": "Muffin",
    "BAKED_GOOD": "Baked Good",
    "COFFEE": "Coffee",
    "COOKIE": "Cookie",
    "COLD Foam": "Cold Foam",
}


def cleanup_orphan_roast_profiles(apps, schema_editor):
    Ingredient = apps.get_model("mscrInventory", "Ingredient")
    RoastProfile = apps.get_model("mscrInventory", "RoastProfile")

    connection = getattr(schema_editor, "connection", None)
    if connection is None:
        from django.db import connections, DEFAULT_DB_ALIAS

        connection = connections[DEFAULT_DB_ALIAS]

    roast_table = RoastProfile._meta.db_table
    ingredient_table = Ingredient._meta.db_table

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            DELETE FROM {roast_table}
            WHERE NOT EXISTS (
                SELECT 1 FROM {ingredient_table}
                WHERE {ingredient_table}.id = {roast_table}.ingredient_ptr_id
            )
            """
        )


def _normalize_selector(selector, type_lookup):
    if not isinstance(selector, dict):
        return selector
    raw = selector.get("by_type") or []
    converted = []
    for value in raw:
        if isinstance(value, int):
            converted.append(value)
            continue
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                continue
            if cleaned.isdigit():
                converted.append(int(cleaned))
                continue
            match = type_lookup.get(cleaned.lower())
            if match:
                converted.append(match)
                continue
    selector["by_type"] = converted
    return selector


def populate_recipe_modifier_types(apps, schema_editor):
    IngredientType = apps.get_model("mscrInventory", "IngredientType")
    RecipeModifier = apps.get_model("mscrInventory", "RecipeModifier")

    existing_types = {
        (name or "").strip().lower(): pk
        for pk, name in IngredientType.objects.values_list("id", "name")
    }

    for modifier in RecipeModifier.objects.all():
        code = getattr(modifier, "type", None)
        display = MODIFIER_TYPE_CHOICES.get(code, code or "Modifier")

        type_obj = None
        for candidate in filter(None, {code, display}):
            lookup = IngredientType.objects.filter(name__iexact=candidate).order_by("id").first()
            if lookup:
                type_obj = lookup
                break
        if not type_obj:
            fallback = display or code or "Modifier"
            type_obj, _ = IngredientType.objects.get_or_create(name=fallback)
            existing_types[(type_obj.name or "").strip().lower()] = type_obj.id

        selector = modifier.target_selector
        selector = _normalize_selector(selector, existing_types)

        modifier.ingredient_type = type_obj
        modifier.target_selector = selector
        modifier.save(update_fields=["ingredient_type", "target_selector"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("mscrInventory", "0020_roastprofile_delete_coffee"),
    ]

    operations = [
        migrations.RunPython(cleanup_orphan_roast_profiles, noop),
        migrations.AddField(
            model_name="recipemodifier",
            name="ingredient_type",
            field=models.ForeignKey(
                related_name="recipe_modifiers",
                null=True,
                on_delete=models.PROTECT,
                to="mscrInventory.ingredienttype",
            ),
        ),
        migrations.RunPython(populate_recipe_modifier_types, noop),
        migrations.AlterField(
            model_name="recipemodifier",
            name="ingredient_type",
            field=models.ForeignKey(
                related_name="recipe_modifiers",
                on_delete=models.PROTECT,
                to="mscrInventory.ingredienttype",
            ),
        ),
        migrations.RemoveField(
            model_name="recipemodifier",
            name="type",
        ),
        migrations.AlterField(
            model_name="recipemodifier",
            name="target_selector",
            field=models.JSONField(
                blank=True,
                help_text='Filter for which ingredients this modifier affects, e.g. {"by_type":[1,2],"by_name":["Bacon"]}',
                null=True,
            ),
        ),
        migrations.AlterModelOptions(
            name="recipemodifier",
            options={"ordering": ["ingredient_type__name", "name"]},
        ),
    ]
