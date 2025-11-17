"""Management command to verify Shopify API credentials."""

from __future__ import annotations

import datetime as dt

import requests
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Ping the Shopify API with the configured credentials."""
    help = "Test connectivity to the configured Shopify store using current environment settings."

    def handle(self, *args, **options):
        api_key = getattr(settings, "SHOPIFY_API_KEY", None) or None
        password = getattr(settings, "SHOPIFY_PASSWORD", None) or None
        access_token = getattr(settings, "SHOPIFY_ACCESS_TOKEN", None) or None
        store_domain = (getattr(settings, "SHOPIFY_STORE_DOMAIN", None) or "").strip()
        api_version = getattr(settings, "SHOPIFY_API_VERSION", "2024-10")

        if store_domain.startswith("https://"):
            store_domain = store_domain[len("https://") :]
        if store_domain.startswith("http://"):
            store_domain = store_domain[len("http://") :]
        store_domain = store_domain.rstrip("/")

        self.stdout.write("🔍 Checking Shopify configuration...\n")
        self.stdout.write(f"  • Store domain: {store_domain or '(missing)'}")
        self.stdout.write(f"  • API version: {api_version}")
        self.stdout.write(f"  • Access token present: {'yes' if access_token else 'no'}")
        self.stdout.write(f"  • API key/password present: {'yes' if api_key and password else 'no'}\n")

        if not store_domain:
            self.stdout.write(self.style.ERROR("❌ SHOPIFY_STORE_DOMAIN is not set."))
            return

        headers: dict[str, str] = {}
        auth = None
        if access_token:
            headers["X-Shopify-Access-Token"] = access_token
        elif api_key and password:
            auth = (api_key, password)
        else:
            self.stdout.write(
                self.style.ERROR("❌ No credentials found. Set SHOPIFY_ACCESS_TOKEN or SHOPIFY_API_KEY/SHOPIFY_PASSWORD.")
            )
            return

        url = f"https://{store_domain}/admin/api/{api_version}/orders/count.json"
        params = {
            "status": "any",
            "financial_status": "any",
            "fulfillment_status": "any",
            "created_at_min": (dt.datetime.utcnow() - dt.timedelta(days=7)).isoformat() + "Z",
            "created_at_max": dt.datetime.utcnow().isoformat() + "Z",
        }

        self.stdout.write(f"🌐 Sending test request to {url}")
        try:
            response = requests.get(url, headers=headers, auth=auth, params=params, timeout=30)
        except requests.RequestException as exc:
            self.stdout.write(self.style.ERROR(f"❌ Network error: {exc}"))
            return

        self.stdout.write(f"📡 Response status: {response.status_code}")
        if response.status_code == 401:
            self.stdout.write(self.style.ERROR("❌ Unauthorized. Check API credentials and store permissions."))
            return
        if response.status_code == 403:
            self.stdout.write(self.style.ERROR("❌ Forbidden. The credentials lack access to the Orders API."))
            return
        if response.status_code >= 400:
            self.stdout.write(self.style.ERROR(f"❌ Shopify returned an error: {response.text[:500]}"))
            return

        try:
            payload = response.json()
        except ValueError:
            self.stdout.write(self.style.ERROR("❌ Could not parse JSON response from Shopify."))
            return

        order_count = payload.get("count")
        if order_count is None:
            self.stdout.write(self.style.WARNING(f"⚠️ Unexpected response payload: {payload}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"✅ Connection successful! Orders in last 7 days: {order_count}"))
