"""Vietnamese price parsing: single, compound and per-m2 forms, and what must NOT be a price."""

import pytest

from real_estate_price_tracking_systems.infrastructure.crawler.parsing.price import (
    MAX_VALID_PRICE_VND,
    parse_vietnamese_price,
)

TY = 1_000_000_000
TRIEU = 1_000_000


@pytest.mark.parametrize(
    ("raw", "total"),
    [
        ("5,2 tỷ", 5.2 * TY),
        ("850 triệu", 850 * TRIEU),
        ("500 k", 500_000),
        ("2.500.000.000 đ", 2.5 * TY),
        (2_500_000_000, 2.5 * TY),
        ("15 triệu/tháng", 15 * TRIEU),  # a rent suffix does not change the amount
    ],
)
def test_single_prices(raw: object, total: float) -> None:
    assert parse_vietnamese_price(raw) == (total, None)


@pytest.mark.parametrize(
    ("raw", "total"),
    [
        ("3 tỷ 500 triệu", 3.5 * TY),
        ("1 tỷ 250 triệu", 1.25 * TY),
        ("2 triệu 500 nghìn", 2.5 * TRIEU),
        ("2 tỷ 5", 2.5 * TY),  # a bare second number reads like a decimal
        ("2 tỷ 25", 2.25 * TY),
        ("2 tỷ 250", 2.25 * TY),
    ],
)
def test_compound_prices(raw: str, total: float) -> None:
    assert parse_vietnamese_price(raw)[0] == total


def test_compound_price_next_to_an_area_ignores_the_area() -> None:
    """'3 tỷ 100 m2' is 3 tỷ followed by an area, not 3.1 tỷ."""
    assert parse_vietnamese_price("3 tỷ 100 m2", area=100) == (3 * TY, 30 * TRIEU)
    assert parse_vietnamese_price("3 tỷ 100m²")[0] == 3 * TY


def test_per_m2_price_derives_the_total_from_the_area() -> None:
    assert parse_vietnamese_price("45 tr/m2", area=80) == (3.6 * TY, 45 * TRIEU)
    assert parse_vietnamese_price("45 tr/m2") == (None, 45 * TRIEU)  # no area: no total


def test_total_price_derives_per_m2() -> None:
    assert parse_vietnamese_price("1 tỷ 250 triệu", area=50) == (1.25 * TY, 25 * TRIEU)
    assert parse_vietnamese_price(2_500_000_000, area=100) == (2.5 * TY, 25 * TRIEU)
    assert parse_vietnamese_price("2 tỷ", area=0) == (2 * TY, None)


@pytest.mark.parametrize(
    "raw", ["thỏa thuận", "Liên hệ", "0", 0, -5, "abc", "", None, "12345", "đang cập nhật"]
)
def test_no_price(raw: object) -> None:
    assert parse_vietnamese_price(raw) == (None, None)


def test_absurd_prices_are_dropped() -> None:
    assert parse_vietnamese_price("9999 tỷ") == (None, None)
    assert parse_vietnamese_price(MAX_VALID_PRICE_VND + 1) == (None, None)
    assert parse_vietnamese_price(MAX_VALID_PRICE_VND)[0] == MAX_VALID_PRICE_VND


def test_per_m2_price_that_implies_an_absurd_total_is_dropped() -> None:
    assert parse_vietnamese_price("1.5 tỷ/m2", area=5000) == (None, None)
