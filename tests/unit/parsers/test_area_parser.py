"""Area and plot-dimension parsing."""

import pytest

from real_estate_price_tracking_systems.infrastructure.crawler.parsing.area import (
    extract_dimensions,
    parse_vietnamese_area,
)


@pytest.mark.parametrize(
    ("raw", "area"),
    [
        ("85,5 m²", 85.5),
        ("85.5 m2", 85.5),
        ("1.200 m2", 1200.0),  # a dot before exactly three digits is a thousand separator
        ("250 m 2", 250.0),  # the superscript lost its markup during text extraction
        ("120 mét vuông", 120.0),
        ("diện tích 85 m2, mặt tiền 5m", 85.0),
        ("100", 100.0),
        (100.5, 100.5),
    ],
)
def test_areas(raw: object, area: float) -> None:
    assert parse_vietnamese_area(raw) == area


@pytest.mark.parametrize(
    "raw",
    [
        "-50 m2",  # the unit regex alone would read this as 50
        "0 m2",
        0,
        -3,
        "5 phòng ngủ",  # a number without an area unit is not an area
        "m2",
        "",
        None,
        6_000_000,  # beyond any plausible lot
        "6000000 m2",
    ],
)
def test_not_an_area(raw: object) -> None:
    assert parse_vietnamese_area(raw) is None


@pytest.mark.parametrize(
    ("text", "dimensions"),
    [
        ("5x20m", (5.0, 20.0)),
        ("5 x 20m", (5.0, 20.0)),
        ("4,5*18", (4.5, 18.0)),
        ("DT: 5x20", (5.0, 20.0)),
        ("mặt tiền 5m dài 20m", (5.0, 20.0)),
        ("ngang 4.5m sâu 18m", (4.5, 18.0)),
        ("mặt tiền 5m", (5.0, None)),
    ],
)
def test_dimensions(text: str, dimensions: tuple[float | None, float | None]) -> None:
    assert extract_dimensions(text) == dimensions


@pytest.mark.parametrize("text", ["85 m2", "", None, "1000x5", "0x5"])
def test_no_dimensions(text: str | None) -> None:
    assert extract_dimensions(text) == (None, None)
