"""Manager-facing dashboard for user and group management."""
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from mscrInventory.forms import UserCreateForm, UserUpdateForm


def _has_user_admin_access(user) -> bool:
    """Return True if the user can administer accounts."""

    return bool(user.is_superuser or user.has_perm("auth.change_user"))


@login_required
def manage_users_groups_view(request):
    """Allow Managers and superusers to manage accounts without Django admin."""

    if not _has_user_admin_access(request.user):
        raise PermissionDenied

    User = get_user_model()
    selected_user = None
    selected_user_id = request.GET.get("user")
    if selected_user_id:
        selected_user = get_object_or_404(User, pk=selected_user_id)

    create_form = UserCreateForm(prefix="create")
    edit_form = UserUpdateForm(prefix="edit", instance=selected_user) if selected_user else None

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            create_form = UserCreateForm(request.POST, prefix="create")
            if create_form.is_valid():
                new_user = create_form.save()
                messages.success(request, f"Created user {new_user.username}.")
                return redirect(f"{reverse('manage_users')}?user={new_user.pk}")
        elif action == "update":
            user_id = request.POST.get("user_id")
            target = get_object_or_404(User, pk=user_id)
            edit_form = UserUpdateForm(request.POST, instance=target, prefix="edit")
            if edit_form.is_valid():
                edit_form.save()
                messages.success(request, f"Updated user {target.username}.")
                return redirect(f"{reverse('manage_users')}?user={target.pk}")

    users = User.objects.order_by("username")
    groups = Group.objects.order_by("name").prefetch_related("permissions", "user_set")

    context = {
        "create_form": create_form,
        "edit_form": edit_form,
        "selected_user": selected_user,
        "users": users,
        "groups": groups,
    }
    return render(request, "user_management.html", context)
