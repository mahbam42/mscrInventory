"""
Import Framework
----------------
Defines BaseImporter and shared logic for specific importers.
Example subclasses: SquareImporter, ShopifyImporter.
"""

import datetime
import tempfile
from pathlib import Path

from django.contrib import messages
from django.core.management import call_command
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from importers.square_importer import SquareImporter
from mscrInventory.models import ImportLog, Ingredient, Product

def imports_dashboard_view(request):
    """Renders the unified imports dashboard."""
    return render(request, "imports/dashboard.html")

"""
Web dashboard view for uploading Square CSVs and running imports (dry-run or live).

This is NOT a Django management command.
It should live under `mscrInventory/views/` and call `SquareImporter`.
"""
@require_POST
def upload_square_view(request):
    """Handle Square CSV upload via dashboard (supports dry run)."""
    uploaded_file = request.FILES.get("square_csv")
    dry_run = bool(request.POST.get("dry_run"))  # Checkbox or hidden input

    if not uploaded_file:
        messages.error(request, "No file uploaded.")
        return redirect("imports_dashboard")

    # Save upload to a temp file
    tmp_path = Path(tempfile.gettempdir()) / uploaded_file.name
    with open(tmp_path, "wb+") as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)

    try:
        importer = SquareImporter(dry_run=dry_run)
        importer.run_from_file(tmp_path)
        output = importer.get_output()

        ImportLog.objects.update_or_create(
            source="square",
            defaults={
                "last_run": timezone.now(),
                "log_excerpt": output[:2000],
            },
        )

        messages.success(
            request,
            f"{'🧪 Dry-run complete' if dry_run else '✅ Import complete'} — {uploaded_file.name}",
        )
        messages.info(request, f"<pre>{output}</pre>")

    except Exception as e:
        messages.error(request, f"❌ Error importing Square CSV: {e}")
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except TypeError:
            if tmp_path.exists():
                tmp_path.unlink()

    return redirect("imports_dashboard")


def unmapped_items_view(request):
    """Return modal/page content summarising unmapped products and ingredients."""
    products = Product.objects.filter(name__startswith="Unmapped:").order_by("name")
    ingredients = Ingredient.objects.filter(name__startswith="Unmapped:").order_by("name")
    context = {"products": products, "ingredients": ingredients}

    if request.headers.get("HX-Request") == "true":
        template = "imports/_unmapped_modal.html"
    else:
        template = "imports/unmapped_items.html"

    return render(request, template, context)


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
            ImportLog.objects.update_or_create(
                source="shopify", defaults={"last_run": timezone.now()}
            )
            messages.success(request, f"✅ Shopify orders fetched for {start_date} → {end_date}")
        else:
            call_command("sync_orders", date=start_date)
            messages.success(request, f"✅ Shopify orders fetched for {start_date}")
    except Exception as e:
        messages.error(request, f"❌ Error fetching Shopify data: {e}")

    return redirect("imports_dashboard")