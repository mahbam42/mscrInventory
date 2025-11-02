"""
Import views for handling external data sources.
"""

import json
import tempfile
from decimal import Decimal
from pathlib import Path

from django import forms as django_forms
from django.contrib import messages
from django.core.management import call_command
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from importers.square_importer import SquareImporter
from mscrInventory.forms import CreateFromUnmappedItemForm, LinkUnmappedItemForm
from mscrInventory.models import ImportLog, Ingredient, Product, SquareUnmappedItem


def _build_unmapped_context(
    filter_type: str | None = None,
    form_overrides: dict | None = None,
    *,
    page: int | str | None = None,
    paginate: bool = False,
    per_page: int = 15,
):
    """Assemble context for unmapped items modal and page views."""

    form_overrides = form_overrides or {}
    allowed_types = {choice[0] for choice in SquareUnmappedItem.ITEM_TYPE_CHOICES}
    selected = filter_type if filter_type in allowed_types else "all"

    unresolved_qs = SquareUnmappedItem.objects.filter(resolved=False, ignored=False).order_by(
        "-last_seen", "item_name"
    )
    filtered_qs = unresolved_qs.filter(item_type=selected) if selected in allowed_types else unresolved_qs

    page_obj = None
    if paginate:
        paginator = Paginator(filtered_qs, per_page)
        try:
            page_obj = paginator.page(page or 1)
        except (EmptyPage, PageNotAnInteger):
            page_obj = paginator.page(1)
        current_items = list(page_obj.object_list)
    else:
        current_items = list(filtered_qs)

    counts = {
        entry["item_type"]: entry["total"]
        for entry in unresolved_qs.values("item_type").annotate(total=Count("id"))
    }

    entries = []
    for item in current_items:
        link_form = form_overrides.get(
            ("link", item.id),
            LinkUnmappedItemForm(item=item, initial={"filter_type": selected}),
        )
        create_form = form_overrides.get(
            ("create", item.id),
            CreateFromUnmappedItemForm(item=item, initial={"filter_type": selected}),
        )
        entries.append({"item": item, "link_form": link_form, "create_form": create_form})

    filter_options = [
        ("all", "All", unresolved_qs.count()),
        *[
            (value, label, counts.get(value, 0))
            for value, label in SquareUnmappedItem.ITEM_TYPE_CHOICES
        ],
    ]

    return {
        "square_items": current_items,
        "square_entries": entries,
        "filter_type": selected,
        "filter_options": filter_options,
        "total_unresolved": unresolved_qs.count(),
        "page_obj": page_obj,
        "ingredients": Ingredient.objects.filter(name__startswith="Unmapped:").order_by("name"),
    }


def imports_dashboard_view(request):
    """Renders the unified imports dashboard."""

    unresolved_count = SquareUnmappedItem.objects.filter(resolved=False, ignored=False).count()
    return render(request, "imports/dashboard.html", {"unresolved_count": unresolved_count})


@require_POST
def upload_square_view(request):
    """Handle Square CSV upload via dashboard (supports dry run)."""

    uploaded_file = request.FILES.get("square_csv")
    dry_run = bool(request.POST.get("dry_run"))

    if not uploaded_file:
        messages.error(request, "No file uploaded.")
        return redirect("imports_dashboard")

    tmp_path = Path(tempfile.gettempdir()) / uploaded_file.name
    with open(tmp_path, "wb+") as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)

    try:
        importer = SquareImporter(dry_run=dry_run)
        importer.run_from_file(tmp_path)
        output = importer.get_output()
        summary = importer.get_summary()
        metadata = importer.get_run_metadata()
        stats = metadata.get("stats", {})
        duration = metadata.get("duration_seconds")
        duration_decimal = Decimal(str(duration)) if duration is not None else None

        ImportLog.objects.create(
            source="square",
            run_type="dry-run" if dry_run else "live",
            filename=uploaded_file.name,
            started_at=metadata.get("started_at"),
            finished_at=metadata.get("finished_at"),
            duration_seconds=duration_decimal,
            rows_processed=stats.get("rows_processed", 0),
            matched_count=stats.get("matched", 0),
            unmatched_count=stats.get("unmatched", 0),
            order_items=stats.get("order_items_logged", 0),
            modifiers_applied=stats.get("modifiers_applied", 0),
            error_count=stats.get("errors", 0),
            summary=summary,
            log_output=output,
            uploaded_by=request.user if request.user.is_authenticated else None,
        )

        messages.success(
            request,
            f"{'🧪 Dry-run complete' if dry_run else '✅ Import complete'} — {uploaded_file.name}",
        )
        messages.info(
            request,
            format_html(
                "<pre class='import-log bg-light p-3 border rounded small mb-0'>{}</pre>",
                summary,
            ),
        )

    except Exception as exc:  # pragma: no cover - defensive logging
        messages.error(request, f"❌ Error importing Square CSV: {exc}")
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except TypeError:
            if tmp_path.exists():
                tmp_path.unlink()

    return redirect("imports_dashboard")


def unmapped_items_view(request):
    """Render modal or page content summarising unmapped entries."""

    filter_type = request.GET.get("type")
    page_number = request.GET.get("page")
    is_modal_request = request.headers.get("HX-Request") == "true"
    paginate = not is_modal_request
    context = _build_unmapped_context(
        filter_type,
        page=page_number if paginate else None,
        paginate=paginate,
    )

    hx_target = request.headers.get("HX-Target")
    if hx_target == "unmapped-items-table":
        template = "partials/unmapped_square_items_table.html"
    elif request.headers.get("HX-Request") == "true":
        template = "imports/_unmapped_modal.html"
    else:
        template = "imports/unmapped_items.html"

    return render(request, template, context)


def _render_unmapped_table(request, filter_type: str | None, form_overrides=None, status=200):
    paginate_flag = request.POST.get("paginate") == "1"
    page_number = request.POST.get("page") if paginate_flag else None
    context = _build_unmapped_context(
        filter_type,
        form_overrides=form_overrides,
        page=page_number,
        paginate=paginate_flag,
    )
    return render(
        request,
        "partials/unmapped_square_items_table.html",
        context,
        status=status,
    )


@require_POST
def link_unmapped_item(request, pk: int):
    item = get_object_or_404(SquareUnmappedItem, pk=pk, ignored=False)
    filter_type = request.POST.get("filter_type") or None

    form = LinkUnmappedItemForm(request.POST, item=item)
    if form.is_valid():
        user = request.user if request.user.is_authenticated else None
        form.save(user=user)
        response = _render_unmapped_table(request, filter_type)
        response["HX-Trigger"] = json.dumps(
            {"showMessage": {"text": "✅ Linked to existing record.", "level": "success"}}
        )
        return response

    overrides = {("link", item.id): form}
    return _render_unmapped_table(request, filter_type, form_overrides=overrides, status=400)


@require_POST
def create_unmapped_item(request, pk: int):
    item = get_object_or_404(SquareUnmappedItem, pk=pk, ignored=False)
    filter_type = request.POST.get("filter_type") or None

    form = CreateFromUnmappedItemForm(request.POST, item=item)
    try:
        if form.is_valid():
            user = request.user if request.user.is_authenticated else None
            form.save(user=user)
            response = _render_unmapped_table(request, filter_type)
            response["HX-Trigger"] = json.dumps(
                {
                    "showMessage": {
                        "text": "✅ Created new record from unmapped item.",
                        "level": "success",
                    }
                }
            )
            return response
    except django_forms.ValidationError as exc:
        form.add_error(None, exc.message)

    overrides = {("create", item.id): form}
    return _render_unmapped_table(request, filter_type, form_overrides=overrides, status=400)


@require_POST
def ignore_unmapped_item(request, pk: int):
    item = get_object_or_404(SquareUnmappedItem, pk=pk)
    filter_type = request.POST.get("filter_type") or None

    user = request.user if request.user.is_authenticated else None
    item.mark_resolved(user=user, ignored=True)

    response = _render_unmapped_table(request, filter_type)
    response["HX-Trigger"] = json.dumps(
        {"showMessage": {"text": "⚠️ Item ignored for now.", "level": "warning"}}
    )
    return response


@require_POST
def bulk_unmapped_action(request):
    action = request.POST.get("action")
    filter_type = request.POST.get("filter_type") or "all"
    allowed_types = {choice[0] for choice in SquareUnmappedItem.ITEM_TYPE_CHOICES}

    qs = SquareUnmappedItem.objects.filter(resolved=False, ignored=False)
    if filter_type in allowed_types:
        qs = qs.filter(item_type=filter_type)

    user = request.user if request.user.is_authenticated else None
    processed = 0

    if action == "resolve":
        for item in qs:
            item.mark_resolved(user=user)
            processed += 1
        if processed:
            messages.success(request, f"✅ Marked {processed} items as resolved.")
    elif action == "ignore":
        for item in qs:
            item.mark_resolved(user=user, ignored=True)
            processed += 1
        if processed:
            messages.warning(request, f"⚠️ Ignored {processed} items.")
    elif action == "create":
        for item in qs:
            name = item.price_point_name or item.item_name
            if item.item_type == "product":
                sku = CreateFromUnmappedItemForm._generate_default_sku(item, fallback=name)
                product = Product.objects.create(name=name, sku=sku)
                item.mark_resolved(user=user, product=product)
                processed += 1
            elif item.item_type == "ingredient":
                ingredient, _created = Ingredient.objects.get_or_create(name=name)
                item.mark_resolved(user=user, ingredient=ingredient)
                processed += 1
        if processed:
            messages.success(request, f"✅ Created {processed} placeholder records.")
        else:
            messages.info(request, "ℹ️ No eligible items to create automatically.")
    else:
        messages.error(request, "❌ Unknown bulk action.")

    redirect_url = f"{reverse('imports_unmapped_items')}?type={filter_type}"
    return redirect(redirect_url)


@require_POST
def fetch_shopify_view(request):
    """Fetch Shopify data for a date or range."""

    start_date = request.POST.get("start_date")
    end_date = request.POST.get("end_date")
    if not start_date:
        messages.error(request, "Start date is required.")
        return redirect("imports_dashboard")

    try:
        if end_date:
            call_command("sync_orders", start=start_date, end=end_date)
            summary = f"Shopify orders fetched for {start_date} → {end_date}"
            ImportLog.objects.create(
                source="shopify",
                run_type="live",
                filename="",
                started_at=timezone.now(),
                finished_at=timezone.now(),
                summary=summary,
                log_output=summary,
                uploaded_by=request.user if request.user.is_authenticated else None,
            )
            messages.success(request, f"✅ {summary}")
        else:
            call_command("sync_orders", date=start_date)
            summary = f"Shopify orders fetched for {start_date}"
            ImportLog.objects.create(
                source="shopify",
                run_type="live",
                filename="",
                started_at=timezone.now(),
                finished_at=timezone.now(),
                summary=summary,
                log_output=summary,
                uploaded_by=request.user if request.user.is_authenticated else None,
            )
            messages.success(request, f"✅ {summary}")
    except Exception as exc:  # pragma: no cover - defensive logging
        messages.error(request, f"❌ Error fetching Shopify data: {exc}")

    return redirect("imports_dashboard")


def import_logs_view(request):
    """Display a paginated history of import logs."""

    logs = ImportLog.objects.select_related("uploaded_by").order_by("-created_at")
    paginator = Paginator(logs, 20)
    page_number = request.GET.get("page")
    try:
        page_obj = paginator.page(page_number or 1)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    return render(
        request,
        "imports/log_list.html",
        {
            "page_obj": page_obj,
        },
    )
