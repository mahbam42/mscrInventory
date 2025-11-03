"""Shopify order importer.

This importer mirrors the Square importer by relying on the shared
``BaseImporter`` utilities for logging/dry-run behaviour and the
``_aggregate_usage`` helpers for consistent ingredient usage math.

The importer fetches Shopify orders for a date window, normalises the
line items so they align with the Square data model, persists the
corresponding ``Order``/``OrderItem`` rows, and tracks ingredient usage
by leveraging ``aggregate_ingredient_usage``. Coffee retail bags are
mapped to the canonical ``Retail Bag`` product with roast metadata so
Shopify and Square stay in sync.
"""

from __future__ import annotations

from collections import defaultdict
import datetime as dt
from decimal import Decimal
from typing import Any, Iterable

import requests
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from importers._aggregate_usage import (
    aggregate_ingredient_usage,
    infer_temp_and_size,
    resolve_modifier_tree,
)
from importers._base_Importer import BaseImporter
from importers._match_product import _extract_descriptors, _normalize_name
from importers.square_importer import (
    RETAIL_BAG_NAMES,
    _extract_retail_bag_details,
    _locate_roast_ingredient,
    _product_is_drink,
)
from mscrInventory.models import (
    Ingredient,
    Order,
    OrderItem,
    Product,
    RecipeModifier,
    get_or_create_roast_profile,
)


def _json_safe(value: Any) -> Any:
    """Render values that Django's JSONField can store."""

    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


class ShopifyImporter(BaseImporter):
    """Importer that fetches and persists Shopify orders."""

    platform = "shopify"

    def __init__(self, *, dry_run: bool = False, log_to_console: bool = True):
        super().__init__(dry_run=dry_run, log_to_console=log_to_console)
        self.usage_totals: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        self._retail_bag_product: Product | None = None
        self.counters.setdefault("matched", 0)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def import_window(
        self,
        start_utc: dt.datetime,
        end_utc: dt.datetime,
        *,
        orders: Iterable[dict[str, Any]] | None = None,
    ) -> dict[int, Decimal]:
        """Import Shopify orders for the provided UTC window."""

        if start_utc.tzinfo is None or end_utc.tzinfo is None:
            raise ValueError("start_utc and end_utc must be timezone-aware")

        if orders is None:
            orders = self._fetch_orders(start_utc, end_utc)

        self.log(
            f"Processing Shopify orders between {start_utc.isoformat()} and {end_utc.isoformat()}",
            "🚚",
        )

        with transaction.atomic():
            for raw_order in orders:
                self.process_row(raw_order)

        self.summarize()
        return dict(self.usage_totals)

    # ------------------------------------------------------------------
    # BaseImporter hook
    # ------------------------------------------------------------------
    def process_row(self, raw_order: dict[str, Any]) -> None:  # type: ignore[override]
        """Normalise and persist a single Shopify order."""

        normalized = self._normalize_order(raw_order)
        order_id = normalized["order_id"]
        line_items = normalized["items"]

        self.log(
            f"Order {order_id}: {len(line_items)} line item(s) totalling {normalized['total_amount']}",
            "🧾",
        )

        order_lookup = {"order_id": order_id, "platform": self.platform}
        defaults = {
            "order_date": normalized["order_date"],
            "total_amount": normalized["total_amount"],
            "data_raw": _json_safe(normalized["raw"]),
            "synced_at": timezone.now(),
        }

        order_obj, created = self.create_or_update(Order, order_lookup, defaults)

        if self.dry_run:
            action = "Would create" if created else "Would update"
            self.log(f"🧪 {action} {len(line_items)} order item(s) for {order_id}")
        else:
            order_obj.items.all().delete()

        for item in line_items:
            product = item.get("product")
            if not product:
                self.counters["unmapped"] += 1
                self.log(
                    f"⚠️  Unmapped Shopify item '{item.get('title')}' (SKU: {item.get('sku')})",
                    "⚠️",
                )
            else:
                self.counters["matched"] = self.counters.get("matched", 0) + 1

            quantity = item.get("quantity", 0)
            if self.dry_run:
                self.log(
                    f"🧪 Would record {quantity}x {item.get('title')} (product={'mapped' if product else 'missing'})",
                    "🧪",
                )
            else:
                variant_payload = _json_safe(item.get("variant_info", {}))
                if quantity > 0:
                    OrderItem.objects.create(
                        order=order_obj,
                        product=product,
                        quantity=quantity,
                        unit_price=item["unit_price"],
                        variant_info=variant_payload,
                    )

            self._track_usage_from_item(item)

    # ------------------------------------------------------------------
    # Normalisation helpers
    # ------------------------------------------------------------------
    def _normalize_order(self, raw_order: dict[str, Any]) -> dict[str, Any]:
        """Return a normalized order structure regardless of source format."""

        if "order_id" in raw_order:
            # Legacy/mock structure from tests.
            order_id = str(raw_order["order_id"])
            order_date = raw_order.get("order_date")
            if isinstance(order_date, str):
                order_date = dt.datetime.fromisoformat(order_date)
            if order_date and order_date.tzinfo is None:
                order_date = timezone.make_aware(order_date)
            total_amount = Decimal(str(raw_order.get("total_amount", "0")))
            line_items = [
                self._normalize_line_item(
                    {
                        "sku": item.get("sku") or item.get("sku_or_handle"),
                        "title": item.get("title") or item.get("name") or item.get("sku_or_handle"),
                        "variant_title": item.get("variant_title") or "",
                        "quantity": item.get("quantity", 0),
                        "price": item.get("unit_price", 0),
                        "product_id": item.get("product_id"),
                    },
                    raw_line=item,
                )
                for item in raw_order.get("items", [])
            ]
            order_date = order_date or timezone.now()
            return {
                "order_id": order_id,
                "order_date": order_date,
                "total_amount": total_amount,
                "items": line_items,
                "raw": raw_order,
            }

        order_id = str(raw_order.get("id") or raw_order.get("name") or "")
        if not order_id:
            raise ValueError("Shopify order missing id")

        created_at = raw_order.get("created_at") or raw_order.get("processed_at")
        if not created_at:
            raise ValueError("Shopify order missing created_at")
        order_date = dt.datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))

        total_price = Decimal(str(raw_order.get("total_price", "0")))
        line_items = [
            self._normalize_line_item(line_item) for line_item in raw_order.get("line_items", [])
        ]

        return {
            "order_id": order_id,
            "order_date": order_date,
            "total_amount": total_price,
            "items": line_items,
            "raw": raw_order,
        }

    def _normalize_line_item(
        self,
        line_item: dict[str, Any],
        *,
        raw_line: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sku = (line_item.get("sku") or "").strip()
        shopify_product_id = line_item.get("product_id")
        title = (line_item.get("title") or line_item.get("name") or sku).strip()
        variant_title = (line_item.get("variant_title") or "").strip()

        normalized_title = _normalize_name(title)
        core_name, title_descriptors = _extract_descriptors(normalized_title)
        normalized_variant = _normalize_name(variant_title)
        _, variant_descriptors = _extract_descriptors(normalized_variant)

        descriptors: list[str] = []
        for token in title_descriptors + variant_descriptors:
            if token and token not in descriptors:
                descriptors.append(token)

        is_retail_bag = False
        title_lower = normalized_title or ""
        variant_lower = normalized_variant or ""
        if title_lower:
            is_retail_bag = any(name in title_lower for name in RETAIL_BAG_NAMES)
        if not is_retail_bag and variant_lower:
            is_retail_bag = any(name in variant_lower for name in RETAIL_BAG_NAMES)
        if not is_retail_bag and "bag" in title_lower and "coffee" in title_lower:
            is_retail_bag = True

        retail_tokens = []
        if normalized_title:
            retail_tokens.append(normalized_title)
        if normalized_variant:
            retail_tokens.append(normalized_variant)

        roast_name = None
        bag_size = None
        grind_label = None
        roast_ingredient = None

        if is_retail_bag:
            roast_name, bag_size, grind_label = _extract_retail_bag_details(retail_tokens)
            roast_ingredient = _locate_roast_ingredient(roast_name)

            if roast_ingredient and not self.dry_run:
                profile = get_or_create_roast_profile(roast_ingredient)
                updates: list[str] = []
                if bag_size and getattr(profile, "bag_size", None) != bag_size:
                    profile.bag_size = bag_size
                    updates.append("bag_size")
                if grind_label and getattr(profile, "grind", None) != grind_label:
                    profile.grind = grind_label
                    updates.append("grind")
                if updates:
                    profile.save(update_fields=updates)
            elif roast_ingredient and self.dry_run:
                self.log(
                    f"🧪 Would ensure roast profile for {roast_ingredient.name} (size={bag_size or 'unchanged'}, grind={grind_label or 'unchanged'})",
                    "🧪",
                )
            elif roast_name:
                self.log(f"⚠️  No roast ingredient found for '{roast_name}'", "⚠️")

        product = self._resolve_product(
            sku=sku,
            title=title,
            normalized_title=normalized_title,
            is_retail_bag=is_retail_bag,
            shopify_product_id=shopify_product_id,
        )

        quantity = int(line_item.get("quantity", 0) or 0)
        unit_price = Decimal(str(line_item.get("price", "0")))

        variant_info = {
            "source": "shopify",
            "title": title,
            "variant_title": variant_title,
            "descriptors": descriptors,
            "normalized_title": normalized_title,
            "normalized_variant": normalized_variant,
            "sku": sku,
        }

        if shopify_product_id:
            variant_info["shopify_product_id"] = str(shopify_product_id)

        if is_retail_bag:
            variant_info["retail_bag"] = {
                "is_retail_bag": True,
                "roast_name": roast_name,
                "bag_size": bag_size,
                "grind": grind_label,
                "roast_ingredient_id": getattr(roast_ingredient, "id", None),
                "roast_ingredient_name": getattr(roast_ingredient, "name", None),
            }
            variant_info["is_drink"] = False
        else:
            variant_info["is_drink"] = _product_is_drink(product)

        if raw_line is not None:
            variant_info["raw_line"] = _json_safe(raw_line)

        return {
            "sku": sku,
            "title": title,
            "quantity": quantity,
            "unit_price": unit_price,
            "product": product,
            "variant_info": variant_info,
        }

    def _resolve_product(
        self,
        *,
        sku: str,
        title: str,
        normalized_title: str,
        is_retail_bag: bool,
        shopify_product_id: Any = None,
    ) -> Product | None:
        """Locate the Product that should back the Shopify line item."""

        if not hasattr(self, "_sku_cache"):
            self._sku_cache: dict[str, Product | None] = {}
        if not hasattr(self, "_shopify_id_cache"):
            self._shopify_id_cache: dict[str, Product | None] = {}

        sku_key = sku.lower()
        if sku_key in self._sku_cache:
            return self._sku_cache[sku_key]

        product: Product | None = None

        if shopify_product_id:
            str_id = str(shopify_product_id)
            if str_id in self._shopify_id_cache:
                product = self._shopify_id_cache[str_id]
            else:
                product = Product.objects.filter(shopify_id=str_id).first()
                self._shopify_id_cache[str_id] = product

        if not product and sku:
            product = Product.objects.filter(sku__iexact=sku).first()

        if not product and title:
            product = Product.objects.filter(name__iexact=title).first()

        if not product and normalized_title:
            product = Product.objects.filter(name__iexact=normalized_title).first()

        if not product and normalized_title:
            product = Product.objects.filter(name__icontains=normalized_title).first()

        if not product and is_retail_bag:
            product = self._get_retail_bag_product()

        if sku:
            self._sku_cache[sku_key] = product

        return product

    def _get_retail_bag_product(self) -> Product | None:
        if self._retail_bag_product is None:
            self._retail_bag_product = (
                Product.objects.filter(name__iexact="retail bag").first()
                or Product.objects.filter(sku__iexact="retail bag").first()
            )
            if not self._retail_bag_product:
                self.log("⚠️  Retail Bag product not found", "⚠️")
        return self._retail_bag_product

    # ------------------------------------------------------------------
    # Ingredient usage tracking
    # ------------------------------------------------------------------
    def _track_usage_from_item(self, item: dict[str, Any]) -> None:
        product: Product | None = item.get("product")
        if not product:
            return

        quantity = Decimal(item.get("quantity", 0) or 0)
        if quantity <= 0:
            return

        variant_info = item.get("variant_info") or {}
        bag_meta = variant_info.get("retail_bag") or {}
        roast_ingredient_id = bag_meta.get("roast_ingredient_id")
        if roast_ingredient_id:
            self.usage_totals[roast_ingredient_id] += quantity
            return

        descriptors: list[str] = variant_info.get("descriptors", [])
        temp_type = variant_info.get("temp_type")
        size = variant_info.get("size")

        if not temp_type or not size:
            inferred_temp, inferred_size = infer_temp_and_size(product.name, descriptors)
            temp_type = temp_type or inferred_temp
            size = size or inferred_size

        resolved_modifiers = []
        for token in descriptors:
            modifier = RecipeModifier.objects.filter(name__iexact=token).first()
            if modifier:
                resolved_modifiers.extend(resolve_modifier_tree(modifier))

        recipe_items = product.recipe_items.select_related("ingredient", "ingredient__type").all()
        usage_summary = aggregate_ingredient_usage(
            recipe_items,
            resolved_modifiers,
            temp_type=temp_type,
            size=size,
            is_drink=variant_info.get("is_drink", _product_is_drink(product)),
        )

        for ingredient_name, data in usage_summary.items():
            ingredient = Ingredient.objects.filter(name__iexact=ingredient_name).first()
            if not ingredient:
                continue
            qty = Decimal(data.get("qty", 0)) * quantity
            self.usage_totals[ingredient.id] += qty

    # ------------------------------------------------------------------
    # Shopify API
    # ------------------------------------------------------------------
    def _fetch_orders(
        self, start_utc: dt.datetime, end_utc: dt.datetime
    ) -> list[dict[str, Any]]:
        api_key = getattr(settings, "SHOPIFY_API_KEY", None) or None
        password = getattr(settings, "SHOPIFY_PASSWORD", None) or None
        store_domain = getattr(settings, "SHOPIFY_STORE_DOMAIN", None) or None

        if not (api_key and password and store_domain):
            self.log("⚠️  Shopify credentials not configured; no orders fetched", "⚠️")
            return []

        url = f"https://{store_domain}/admin/api/2024-10/orders.json"
        params = {
            "status": "any",
            "financial_status": "any",
            "fulfillment_status": "any",
            "created_at_min": start_utc.isoformat().replace("+00:00", "Z"),
            "created_at_max": end_utc.isoformat().replace("+00:00", "Z"),
            "limit": 250,
            "fields": "id,created_at,total_price,line_items,name",
        }

        try:
            response = requests.get(url, auth=(api_key, password), params=params, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:  # pragma: no cover - network failure path
            self.log(f"❌ Shopify API error: {exc}", "❌")
            return []

        payload = response.json() or {}
        return payload.get("orders", [])

