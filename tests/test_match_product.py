import pytest

from importers._match_product import _find_best_product_match, _match_variant_by_name
from tests.factories import CategoryFactory, ProductFactory


@pytest.mark.django_db
def test_exact_match_precedes_partial_candidates():
    matcha = ProductFactory(name="Banana Bread Matcha")
    ProductFactory(name="Banana Bread Latte")

    product, reason = _find_best_product_match("Banana Bread Matcha", "", [])

    assert product == matcha
    assert reason == "exact"


@pytest.mark.django_db
def test_variant_partial_prefers_most_specific_name():
    base = ProductFactory(name="Banana Bread Latte")
    ProductFactory(name="Iced Banana Bread Latte Deluxe")

    product, reason = _match_variant_by_name("Banana Bread")

    assert product == base
    assert reason == "variant_partial"


@pytest.mark.django_db
def test_partial_core_fallback_prefers_shortest_match():
    base_category = CategoryFactory(name="base_item")
    ProductFactory(name="Iced Banana Bread Latte Deluxe", categories=[base_category])
    shorter = ProductFactory(name="Banana Bread", categories=[base_category])

    product, reason = _find_best_product_match("Bread", "", [])

    assert product == shorter
    assert reason == "base_fallback"


@pytest.mark.django_db
def test_fuzzy_conflict_rejects_mismatched_tokens():
    ProductFactory(name="Banana Bread Matcha")

    product, reason = _find_best_product_match("Banana Bread Latte", "", [])

    assert product is None
    assert reason == "fuzzy_conflict"
