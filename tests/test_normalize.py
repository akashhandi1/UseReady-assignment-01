"""Unit tests for the output-formatting layer."""
from src.normalize import (
    normalize_date,
    normalize_days,
    normalize_name,
    normalize_value,
)


def test_value_strips_currency_and_commas():
    assert normalize_value("Rs.9,000/-") == "9000"
    assert normalize_value("10000") == "10000"
    assert normalize_value("") == ""


def test_days_keeps_digits():
    assert normalize_days("90 days") == "90"
    assert normalize_days("60") == "60"


def test_date_zero_pads():
    assert normalize_date("1.4.2010") == "01.04.2010"
    assert normalize_date("01.04.2010") == "01.04.2010"


def test_date_allows_impossible_calendar_dates():
    # ground truth contains derived/invalid dates that must be preserved
    assert normalize_date("31.02.2011") == "31.02.2011"
    assert normalize_date("31.11.2009") == "31.11.2009"


def test_date_handles_iso_order():
    assert normalize_date("2010-04-01") == "01.04.2010"


def test_name_collapses_whitespace():
    assert normalize_name("  P C  MATHEW  ") == "P C MATHEW"
    assert normalize_name("L GOPINATH ") == "L GOPINATH"
