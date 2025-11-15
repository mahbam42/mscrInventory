from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from mscrInventory.models import Product


class ProductFormTests(TestCase):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user("tester", password="pw")
        perm = Permission.objects.get(
            content_type__app_label="mscrInventory",
            codename="change_product",
        )
        self.user.user_permissions.add(perm)
        self.client.force_login(self.user)

    def test_create_product_generates_sku_when_blank(self):
        response = self.client.post(
            reverse("recipes_create_product"),
            {"name": "Auto SKU Latte", "sku": "", "categories": []},
        )

        self.assertEqual(response.status_code, 204)

        product = Product.objects.get()
        self.assertEqual(product.name, "Auto SKU Latte")
        self.assertTrue(product.sku)
