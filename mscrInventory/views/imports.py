"""
Import views for handling external data sources.
"""

import datetime
import json
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django import forms as django_forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.conf import settings
from django.core.management import call_command
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, Exists, OuterRef
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.html import format_html
from django.views.decorators.http import require_POST

from importers.square_importer import SquareImporter
from mscrInventory.forms import CreateFromUnmappedItemForm, LinkUnmappedItemForm
from mscrInventory.models import ImportLog, Ingredient, Product, SquareUnmappedItem
from mscrInventory.management.commands.sync_orders import write_usage_logs


def _should_include_known(values) -> bool:
    """Determine whether known recipes should be included based on request params."""

    truthy = {"1", "true", "on", "yes"}
    for value in values or []:
        if value is None:
            continue
        if str(value).strip().lower() in truthy:
            return True
    return False


def _build_unmapped_context(
    filter_type: str | None = None,
    form_overrides: dict | None = None,
    *,
    page: int | str | None = None,
    paginate: bool = False,
    per_page: int = 15,
    include_known: bool = False,
):
    """Assemble context for unmapped items modal and page views."""

    form_overrides = form_overrides or {}
    allowed_types = {choice[0] for choice in SquareUnmappedItem.ITEM_TYPE_CHOICES}
    selected = filter_type if filter_type in allowed_types else "all"

    product_match = Product.objects.filter(name__iexact=OuterRef("item_name"))
    product_name_list = list(
        Product.objects.order_by("name").values_list("name", flat=True)
    )

    unresolved_qs = (
        SquareUnmappedItem.objects.filter(resolved=False, ignored=False)
        .annotate(is_known_recipe=Exists(product_match))
        .order_by("-last_seen", "item_name")
    )

    type_filtered_qs = (
        unresolved_qs.filter(item_type=selected) if selected in allowed_types else unresolved_qs
    )

    known_recipe_count = type_filtered_qs.filter(is_known_recipe=True).count()

    filtered_qs = type_filtered_qs
    if not include_known:
        filtered_qs = filtered_qs.filter(is_known_recipe=False)

    visible_unresolved_qs = (
        unresolved_qs if include_known else unresolved_qs.filter(is_known_recipe=False)
    )

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

    for item in current_items:
        item.is_known_recipe = bool(getattr(item, "is_known_recipe", False))

    counts = {
        entry["item_type"]: entry["total"]
        for entry in visible_unresolved_qs.values("item_type").annotate(total=Count("id"))
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
        ("all", "All", visible_unresolved_qs.count()),
        *[
            (value, label, counts.get(value, 0))
            for value, label in SquareUnmappedItem.ITEM_TYPE_CHOICES
        ],
    ]

    unmapped_by_type = {}
    for item_type, label in SquareUnmappedItem.ITEM_TYPE_CHOICES:
        type_items = list(visible_unresolved_qs.filter(item_type=item_type))
        for item in type_items:
            item.is_known_recipe = bool(getattr(item, "is_known_recipe", False))
        unmapped_by_type[item_type] = {
            "label": label,
            "items": type_items,
            "total": len(type_items),
        }

    return {
        "square_items": current_items,
        "square_entries": entries,
        "filter_type": selected,
        "filter_options": filter_options,
        "total_unresolved": visible_unresolved_qs.count(),
        "page_obj": page_obj,
        "include_known": include_known,
        "known_recipe_count": known_recipe_count,
        "product_name_list": product_name_list,
        "ingredients": Ingredient.objects.filter(name__startswith="Unmapped:").order_by("name"),
        "unmapped_by_type": unmapped_by_type,
    }


def _save_square_upload(uploaded_file) -> Path:
    """Persist the uploaded Square CSV into the configured directory."""

    target_dir = Path(settings.SQUARE_CSV_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)

    original_name = Path(uploaded_file.name or "square-upload")
    base = slugify(original_name.stem) or "square-upload"
    extension = original_name.suffix
    timestamp = timezone.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{timestamp}-{base}{extension}"

    destination = target_dir / filename
    with destination.open("wb") as handle:
        for chunk in uploaded_file.chunks():
            handle.write(chunk)

    return destination


@permission_required("mscrInventory.view_ingredient", raise_exception=True)
@login_required
def imports_dashboard_view(request):
    """Renders the unified imports dashboard."""

    unresolved_count = SquareUnmappedItem.objects.filter(resolved=False, ignored=False).count()
    return render(request, "imports/dashboard.html", {"unresolved_count": unresolved_count})


@permission_required("mscrInventory.change_ingredient", raise_exception=True)
@require_POST
def upload_square_view(request):
    """Handle Square CSV upload via dashboard (supports dry run)."""

    uploaded_file = request.FILES.get("square_csv")
    dry_run = bool(request.POST.get("dry_run"))

    if not uploaded_file:
        messages.error(request, "No file uploaded.")
        return redirect("imports_dashboard")

    saved_path = _save_square_upload(uploaded_file)

    try:
        importer = SquareImporter(dry_run=dry_run)
        importer.run_from_file(saved_path)
        output = importer.get_output()
        summary = importer.get_summary()
        metadata = importer.get_run_metadata()
        stats = metadata.get("stats", {})
        duration = metadata.get("duration_seconds")
        duration_decimal = Decimal(str(duration)) if duration is not None else None

        ImportLog.objects.create(
            source="square",
            run_type="dry-run" if dry_run else "live",
            filename=saved_path.name,
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

        if not dry_run:
            usage_totals = importer.get_usage_totals()
            if usage_totals:
                business_date_raw = request.POST.get("business_date")
                target_date = timezone.localdate()
                if business_date_raw:
                    try:
                        target_date = datetime.date.fromisoformat(business_date_raw)
                    except ValueError:
                        messages.warning(
                            request,
                            format_html(
                                "⚠️ Invalid business date '{}'. Using {} instead.",
                                business_date_raw,
                                target_date.isoformat(),
                            ),
                        )

                write_usage_logs(target_date, usage_totals, source="square")
                breakdown = importer.get_usage_breakdown() or {}
                detail_snippets: list[str] = []
                for ingredient_name, per_source in sorted(breakdown.items()):
                    total_qty = sum(per_source.values(), Decimal("0"))
                    detail_snippets.append(
                        f"{ingredient_name} × {total_qty.quantize(Decimal('0.001'))}"
                    )
                if detail_snippets:
                    messages.success(
                        request,
                        "📊 Logged Square usage: " + "; ".join(detail_snippets),
                    )
                else:
                    messages.success(
                        request,
                        f"📊 Logged Square usage for {len(usage_totals)} ingredient(s).",
                    )
            else:
                messages.warning(
                    request,
                    "⚠️ Square import completed, but no ingredient usage was detected to log.",
                )

    except Exception as exc:  # pragma: no cover - defensive logging
        messages.error(request, f"❌ Error importing Square CSV: {exc}")

    return redirect("imports_dashboard")


@permission_required("mscrInventory.change_ingredient", raise_exception=True)
def unmapped_items_view(request):
    """Render modal or page content summarising unmapped entries."""

    filter_type = request.GET.get("type")
    page_number = request.GET.get("page")
    include_known = _should_include_known(request.GET.getlist("include_known"))
    is_modal_request = request.headers.get("HX-Request") == "true"
    paginate = not is_modal_request
    context = _build_unmapped_context(
        filter_type,
        page=page_number if paginate else None,
        paginate=paginate,
        include_known=include_known,
    )

    hx_target = (request.headers.get("HX-Target") or "").lstrip("#")
    if hx_target == "unmapped-body":
        template = "imports/_unmapped_body.html"
    elif hx_target == "unmapped-items-table":
        template = "partials/unmapped_square_items_table.html"
    elif request.headers.get("HX-Request") == "true":
        template = "imports/_unmapped_modal.html"
    else:
        template = "imports/unmapped_items.html"

    return render(request, template, context)


def _render_unmapped_table(request, filter_type: str | None, form_overrides=None, status=200):
    """Render the unmapped table partial and optionally override forms."""
    paginate_flag = request.POST.get("paginate") == "1"
    page_number = request.POST.get("page") if paginate_flag else None
    include_known = _should_include_known(request.POST.getlist("include_known"))
    context = _build_unmapped_context(
        filter_type,
        form_overrides=form_overrides,
        page=page_number,
        paginate=paginate_flag,
        include_known=include_known,
    )
    hx_target = (request.headers.get("HX-Target") or "").lstrip("#")
    template = "imports/_unmapped_body.html" if hx_target == "unmapped-body" else "partials/unmapped_square_items_table.html"
    return render(
        request,
        template,
        context,
        status=status,
    )


@permission_required("mscrInventory.change_ingredient", raise_exception=True)
@require_POST
def link_unmapped_item(request, pk: int):
    """Resolve a SquareUnmappedItem by linking to an existing record."""
    item = get_object_or_404(SquareUnmappedItem, pk=pk, ignored=False)
    filter_type = request.POST.get("filter_type") or None
    item.is_known_recipe = Product.objects.filter(name__iexact=item.item_name).exists()

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


@permission_required("mscrInventory.change_ingredient", raise_exception=True)
@require_POST
def create_unmapped_item(request, pk: int):
    """Create a Product/Ingredient/Modifier from an unmapped entry."""
    item = get_object_or_404(SquareUnmappedItem, pk=pk, ignored=False)
    filter_type = request.POST.get("filter_type") or None
    item.is_known_recipe = Product.objects.filter(name__iexact=item.item_name).exists()

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


@permission_required("mscrInventory.change_ingredient", raise_exception=True)
@require_POST
def ignore_unmapped_item(request, pk: int):
    """Hide an unmapped entry without resolving it."""
    item = get_object_or_404(SquareUnmappedItem, pk=pk)
    filter_type = request.POST.get("filter_type") or None

    user = request.user if request.user.is_authenticated else None
    item.mark_resolved(user=user, ignored=True)

    response = _render_unmapped_table(request, filter_type)
    response["HX-Trigger"] = json.dumps(
        {"showMessage": {"text": "⚠️ Item ignored for now.", "level": "warning"}}
    )
    return response


@permission_required("mscrInventory.change_ingredient", raise_exception=True)
@require_POST
def bulk_unmapped_action(request):
    """Apply a batch link/create action to selected unmapped entries."""
    action = request.POST.get("action")
    filter_type = request.POST.get("filter_type") or "all"
    allowed_types = {choice[0] for choice in SquareUnmappedItem.ITEM_TYPE_CHOICES}
    include_known = _should_include_known(request.POST.getlist("include_known"))

    qs = SquareUnmappedItem.objects.filter(resolved=False, ignored=False)
    if filter_type in allowed_types:
        qs = qs.filter(item_type=filter_type)

    if not include_known:
        product_match = Product.objects.filter(name__iexact=OuterRef("item_name"))
        qs = qs.annotate(_known_recipe=Exists(product_match)).filter(_known_recipe=False)

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
    if include_known:
        redirect_url += "&include_known=true"
    return redirect(redirect_url)


@permission_required("mscrInventory.change_ingredient", raise_exception=True)
@require_POST
def fetch_shopify_view(request):
    """Trigger Shopify importer via management command and surface output."""
    """Fetch Shopify data for a date or range."""

    start_date = request.POST.get("start_date")
    end_date = request.POST.get("end_date")
    if not start_date:
        messages.error(request, "Start date is required.")
        return redirect("imports_dashboard")

    output_buffer = StringIO()
    started_at = timezone.now()
    try:
        if end_date:
            call_command(
                "sync_orders",
                start_date=start_date,
                end_date=end_date,
                verbosity=2,
                stdout=output_buffer,
                stderr=output_buffer,
            )
            summary = f"Shopify orders fetched for {start_date} → {end_date}"
        else:
            call_command(
                "sync_orders",
                date=start_date,
                verbosity=2,
                stdout=output_buffer,
                stderr=output_buffer,
            )
            summary = f"Shopify orders fetched for {start_date}"
        finished_at = timezone.now()
        duration_seconds = (finished_at - started_at).total_seconds()
        log_output = output_buffer.getvalue() or summary

        ImportLog.objects.create(
            source="shopify",
            run_type="live",
            filename="",
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=Decimal(str(duration_seconds)),
            summary=summary,
            log_output=log_output,
            uploaded_by=request.user if request.user.is_authenticated else None,
        )
        messages.success(request, f"✅ {summary}")
        if log_output and log_output != summary:
            messages.info(
                request,
                format_html(
                    "<pre class='import-log bg-light p-3 border rounded small mb-0'>{}</pre>",
                    log_output,
                ),
            )
    except Exception as exc:  # pragma: no cover - defensive logging
        finished_at = timezone.now()
        log_output = output_buffer.getvalue()
        messages.error(request, f"❌ Error fetching Shopify data: {exc}")
        if log_output:
            messages.error(
                request,
                format_html(
                    "<pre class='import-log bg-light p-3 border rounded small mb-0'>{}</pre>",
                    log_output,
                ),
            )

    return redirect("imports_dashboard")


def import_logs_view(request):
    """List ImportLog rows with optional AJAX partial rendering."""
    """Display a paginated history of import logs."""

    logs = ImportLog.objects.select_related("uploaded_by").order_by("-created_at")
    unresolved_qs = SquareUnmappedItem.objects.filter(resolved=False, ignored=False).order_by(
        "-last_seen", "item_name"
    )
    unmapped_preview = list(unresolved_qs[:5])
    unmapped_total = unresolved_qs.count()

    error_qs = ImportLog.objects.filter(error_count__gt=0)
    error_preview = list(error_qs.order_by("-created_at")[:5])
    error_total = error_qs.count()
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
            "unmapped_preview": unmapped_preview,
            "unmapped_total": unmapped_total,
            "error_preview": error_preview,
            "error_total": error_total,
        },
    )
