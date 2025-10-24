from pathlib import Path
import tempfile
from django.core.management.base import BaseCommand
from django.shortcuts import redirect
from django.contrib import messages
from django.views.decorators.http import require_POST
from importers import SquareImporter
from mscrInventory.models import ImportLog

from django.utils import timezone

""" ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Temporary partial view definition to handle Square CSV uploads. Moved to imports.py. 10/24/2025
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
        # Create and run the importer
        from importers import SquareImporter
        importer = SquareImporter(dry_run=dry_run)
        importer.run_from_file(tmp_path)

        # Save or update log *inside this block* where importer exists
        ImportLog.objects.update_or_create(
            source="square",
            defaults={
                "last_run": timezone.now(),
                "log_excerpt": importer.buffer.getvalue()[:2000],  # ✅ now in scope
            },
        )

        summary = importer.buffer.getvalue()
        messages.success(
            request,
            f"{'🧪 Dry-run complete' if dry_run else '✅ Import complete'} — {uploaded_file.name}",
        )
        messages.info(request, f"<pre>{summary}</pre>")

    except Exception as e:
        messages.error(request, f"❌ Error importing Square CSV: {e}")

    return redirect("imports_dashboard")
