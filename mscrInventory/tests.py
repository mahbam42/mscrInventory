from django.test import TestCase
from django.urls import reverse

from mscrInventory.models import Product


class ProductFormTests(TestCase):
    def test_create_product_generates_sku_when_blank(self):
        response = self.client.post(
            reverse("recipes_create_product"),
            {"name": "Auto SKU Latte", "sku": "", "categories": []},
        )

        self.assertEqual(response.status_code, 204)

        product = Product.objects.get()
        self.assertEqual(product.name, "Auto SKU Latte")
        self.assertTrue(product.sku)
