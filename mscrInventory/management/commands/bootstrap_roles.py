from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


ROLE_DEFS = {
    "Manager": {
        "prefixes": ["view_", "add_", "change_"],
        "extra_perms": [
            "auth.add_user",
            "auth.change_user",
            "auth.view_user",
            "auth.add_group",
            "auth.change_group",
            "auth.view_group",
        ],
    },
    "Barista": {
        "prefixes": ["view_"],
        "extra_perms": [
            "mscrInventory.add_recipe",
            "mscrInventory.change_recipe",
            "mscrInventory.add_recipeitem",
            "mscrInventory.change_recipeitem",
            "mscrInventory.view_recipeitem",
            "mscrInventory.add_modifier",
            "mscrInventory.change_modifier",
            "mscrInventory.add_recipemodifier",
            "mscrInventory.change_recipemodifier",
            "mscrInventory.add_ingredient",
            "mscrInventory.change_ingredient",
            "mscrInventory.add_inventory",
            "mscrInventory.change_inventory",
        ],
    },
    "Inventory": {
        "prefixes": ["view_"],
        "extra_perms": [
            "mscrInventory.add_inventory",
            "mscrInventory.change_inventory",
        ],
    },
}


def _resolve_permission(label: str) -> Permission | None:
    """Return a permission from `app_label.codename` or `codename`."""

    lookup = {}
    if "." in label:
        app_label, codename = label.split(".", 1)
        lookup["content_type__app_label"] = app_label
    else:
        codename = label
    lookup["codename"] = codename
    try:
        return Permission.objects.get(**lookup)
    except Permission.DoesNotExist:
        return None


class Command(BaseCommand):
    help = "Bootstrap default MSCR user groups and permissions."

    def handle(self, *args, **options):
        perms = Permission.objects.all()
        for role, cfg in ROLE_DEFS.items():
            group, _ = Group.objects.get_or_create(name=role)
            selected = {
                p
                for p in perms
                if any(p.codename.startswith(prefix) for prefix in cfg["prefixes"])
            }
            for label in cfg.get("extra_perms", []):
                perm = _resolve_permission(label)
                if perm:
                    selected.add(perm)
            group.permissions.set(selected)
            self.stdout.write(
                self.style.SUCCESS(f"Synced group {role}: {len(selected)} perms")
            )
