"""Phone normalisation and extraction."""

import pytest

from real_estate_price_tracking_systems.infrastructure.crawler.parsing.phone import (
    extract_phone_from_text,
    parse_vietnamese_phone,
)


@pytest.mark.parametrize(
    ("raw", "phone"),
    [
        ("0901234567", "0901234567"),
        ("0901 234 567", "0901234567"),
        ("+84 901 234 567", "0901234567"),
        ("84901234567", "0901234567"),
        ("tel:0901234567", "0901234567"),
        ("901234567", "0901234567"),  # the leading 0 was dropped by a spreadsheet or JSON number
        ("02439876543", "02439876543"),  # Hanoi landline
        ("https://zalo.me/0901234567", "0901234567"),
        ("/moi-gioi/0912345678", "0912345678"),
    ],
)
def test_normalised_phone(raw: str, phone: str) -> None:
    assert parse_vietnamese_phone(raw) == phone


@pytest.mark.parametrize("raw", ["0123456789", "123", "", None, "1900123456", "090123456"])
def test_not_a_phone(raw: str | None) -> None:
    """Wrong prefixes, wrong lengths and service numbers must not be stored as a contact."""
    assert parse_vietnamese_phone(raw) is None


@pytest.mark.parametrize(
    "text",
    [
        "LH: 0901.234.567 gặp Anh",
        "gọi O9O1234567",  # letter O typed for the digit 0
        "(0901) 234-567",
        "Liên hệ 0901 234 567 để xem nhà",
    ],
)
def test_phone_found_in_free_text(text: str) -> None:
    assert extract_phone_from_text(text) == "0901234567"


@pytest.mark.parametrize("text", ["không có số", "", None, "giá 3 tỷ 500 triệu"])
def test_no_phone_in_text(text: str | None) -> None:
    assert extract_phone_from_text(text) is None
