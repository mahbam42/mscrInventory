import pytest
from django.contrib.auth.models import Group, Permission
from django.core.management import call_command

from mscrInventory.management.commands.bootstrap_roles import (
    ROLE_DEFS,
    _resolve_permission,
)


@pytest.mark.django_db
@pytest.mark.parametrize("group_name", sorted(ROLE_DEFS.keys()))
def test_bootstrap_roles_assigns_expected_permissions(group_name):
    call_command("bootstrap_roles")

    group = Group.objects.get(name=group_name)
    assigned = set(group.permissions.values_list("codename", flat=True))

    cfg = ROLE_DEFS[group_name]
    expected = {
        perm.codename
        for perm in Permission.objects.all()
        if any(perm.codename.startswith(prefix) for prefix in cfg["prefixes"])
    }
    for label in cfg.get("extra_perms", []):
        perm = _resolve_permission(label)
        if perm:
            expected.add(perm.codename)

    assert assigned == expected
