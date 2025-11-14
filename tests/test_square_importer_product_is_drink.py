import pytest

from importers.square_importer import _product_is_drink
from mscrInventory.models import Category, Product


@pytest.mark.django_db
def test_product_is_drink_includes_catering_categories():
    category = Category.objects.create(name="Catering")
    product = Product.objects.create(name="Catering Hot and Cold Box", sku="CAT-BOX")
    product.categories.add(category)

    assert _product_is_drink(product) is True


@pytest.mark.django_db
def test_product_is_drink_still_false_without_matching_categories():
    product = Product.objects.create(name="Bulk Beans", sku="BULK-1")

    assert _product_is_drink(product) is False
