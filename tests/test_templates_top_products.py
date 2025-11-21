from decimal import Decimal

import pytest
from django.template.loader import render_to_string


@pytest.mark.django_db
def test_top_products_modifiers_toggle_renders_truncated_list():
    context = {
        "top_products": [
            {
                "rank": 1,
                "product_name": "Latte",
                "variant_count": 0,
                "variant_details": [],
                "adjectives": (),
                "suppressed_descriptors": (),
                "modifiers": ["a", "b", "c", "d", "e", "f"],
                "quantity": Decimal("5"),
                "gross_sales": Decimal("25.00"),
                "rank_delta": None,
            }
        ]
    }

    html = render_to_string("reports/widgets/_top_products.html", context)

    assert "modifier-toggle" in html
    assert "a, b, c, d, e" in html
    assert "a, b, c, d, e, f" in html
