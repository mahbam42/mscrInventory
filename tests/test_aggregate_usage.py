from decimal import Decimal

from importers._aggregate_usage import get_default_cup, get_scale, infer_temp_and_size


def test_infer_temp_and_size_detects_growler_from_name():
    temp, size = infer_temp_and_size("Cold Brew Growler")
    assert temp == "cold"
    assert size == "growler"


def test_infer_temp_and_size_detects_growler_from_descriptor():
    temp, size = infer_temp_and_size("Cold Brew", ["64oz"])
    assert temp == "cold"
    assert size == "growler"


def test_get_scale_and_cup_for_growler():
    assert get_scale("cold", "growler") == Decimal("4.0")
    assert get_default_cup("cold", "growler") == "64oz Growler"


def test_infer_temp_and_size_detects_keg_from_name():
    temp, size = infer_temp_and_size("Nitro Cold Brew Retail Keg")
    assert temp == "cold"
    assert size == "keg"


def test_infer_temp_and_size_detects_keg_from_descriptor():
    temp, size = infer_temp_and_size("Nitro Cold Brew", ["5 gallon"])
    assert temp == "cold"
    assert size == "keg"


def test_get_scale_and_cup_for_keg():
    assert get_scale("cold", "keg") == Decimal("54.0")
    assert get_default_cup("cold", "keg") == "5gal Retail Keg"
