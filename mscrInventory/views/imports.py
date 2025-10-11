
import datetime
import tempfile
from pathlib import Path

from django.contrib import messages
from django.core.files.storage import default_storage
from django.shortcuts import render, redirect
from django.views.decorators.http import require_POST

from django.core.management import call_command

def imports_dashboard_view(request):
    """Renders the unified imports dashboard."""
    return render(request, "imports/dashboard.html")


@require_POST
def upload_square_view(request):
    """Handle Square CSV upload."""
    uploaded_file = request.FILES.get("square_csv")
    if not uploaded_file:
        messages.error(request, "No file uploaded.")
        return redirect("imports_dashboard")

    tmp_path = Path(tempfile.gettempdir()) / uploaded_file.name
    with open(tmp_path, "wb+") as f:
        for chunk in uploaded_file.chunks():
            f.write(chunk)

    try:
        call_command("import_square_csv", file=str(tmp_path))
        messages.success(request, f"✅ Imported Square CSV: {uploaded_file.name}")
    except Exception as e:
        messages.error(request, f"❌ Error importing Square CSV: {e}")

    return redirect("imports_dashboard")


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
            messages.success(request, f"✅ Shopify orders fetched for {start_date} → {end_date}")
        else:
            call_command("sync_orders", date=start_date)
            messages.success(request, f"✅ Shopify orders fetched for {start_date}")
    except Exception as e:
        messages.error(request, f"❌ Error fetching Shopify data: {e}")

    return redirect("imports_dashboard")

# def imports_dashboard_view(request):
#     """Dashboard with Square CSV upload + Shopify fetch form."""
#     return render(request, "imports/dashboard.html", {})

# @require_POST
# def handle_square_upload(request):
#     """Handle Square CSV file upload and run import command."""
#     uploaded_file = request.FILES.get("square_csv")
#     if not uploaded_file:
#         messages.error(request, "No file uploaded.")
#         return redirect("imports_dashboard")

#     # Save to a temporary file
#     tmp_path = Path(tempfile.gettempdir()) / uploaded_file.name
#     with open(tmp_path, "wb+") as destination:
#         for chunk in uploaded_file.chunks():
#             destination.write(chunk)

#     try:
#         call_command("import_square_csv", file=str(tmp_path))
#         messages.success(request, f"✅ Square CSV '{uploaded_file.name}' imported successfully.")
#     except Exception as e:
#         messages.error(request, f"❌ Error importing Square CSV: {e}")

#     return redirect("imports_dashboard")


# @require_POST
# def fetch_shopify_view(request):
#     """Trigger Shopify sync for a date or range."""
#     start_date = request.POST.get("start_date")
#     end_date = request.POST.get("end_date")

#     if not start_date:
#         messages.error(request, "Start date is required.")
#         return redirect("imports_dashboard")

#     try:
#         # If no end date, just fetch single date
#         if not end_date:
#             call_command("sync_orders", date=start_date)
#             messages.success(request, f"✅ Shopify orders fetched for {start_date}.")
#         else:
#             call_command("sync_orders", start=start_date, end=end_date)
#             messages.success(request, f"✅ Shopify orders fetched for {start_date} → {end_date}.")
#     except Exception as e:
#         messages.error(request, f"❌ Error fetching Shopify data: {e}")

#     return redirect("imports_dashboard")
