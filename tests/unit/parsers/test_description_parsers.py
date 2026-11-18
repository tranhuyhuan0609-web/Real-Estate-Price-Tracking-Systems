"""Road width, legal status and JSON path lookup."""

from typing import Any

import pytest

from real_estate_price_tracking_systems.infrastructure.crawler.parsing.json_path import (
    extract_by_json_path,
)
from real_estate_price_tracking_systems.infrastructure.crawler.parsing.legal_status import (
    extract_legal_status,
)
from real_estate_price_tracking_systems.infrastructure.crawler.parsing.road_width import (
    extract_road_width,
)


@pytest.mark.parametrize(
    ("text", "width"),
    [
        ("đường trước nhà rộng 6m", 6.0),
        ("hẻm 3.5m", 3.5),
        ("hẻm 3,5 mét", 3.5),
        ("ô tô tránh đường 8m", 8.0),
        ("mặt ngõ 4m", 4.0),
        ("10m đường", 10.0),
    ],
)
def test_road_width(text: str, width: float) -> None:
    assert extract_road_width(text) == width


@pytest.mark.parametrize(
    "text",
    [
        "đường 0.5m",  # narrower than a footpath: a typo
        "đường 500m",  # a distance, not a width
        "diện tích 100m2 đường",  # an area, not a width
        "ngõ 3m2",
        "",
        None,
    ],
)
def test_no_road_width(text: str | None) -> None:
    assert extract_road_width(text) is None


@pytest.mark.parametrize(
    ("text", "status"),
    [
        ("Nhà có sổ đỏ chính chủ", "Sổ đỏ/hồng chính chủ"),
        ("sổ hồng chính chủ", "Sổ đỏ/hồng chính chủ"),
        ("sổ hồng riêng", "Sổ đỏ/hồng"),
        ("SỔ ĐỎ", "Sổ đỏ/hồng"),
        ("HĐMB", "Hợp đồng mua bán"),
        ("giấy tờ hợp lệ", "Pháp lý hợp lệ"),
        ("đang chờ cấp sổ", "Chờ cấp sổ"),
        ("vi bằng", "Giấy viết tay/Vi bằng"),
    ],
)
def test_legal_status(text: str, status: str) -> None:
    assert extract_legal_status(text) == status


def test_the_more_specific_legal_status_wins() -> None:
    """'sổ đỏ chính chủ' also contains 'sổ đỏ'; the first, more specific pattern must win."""
    assert extract_legal_status("sổ đỏ chính chủ, sổ đỏ") == "Sổ đỏ/hồng chính chủ"


@pytest.mark.parametrize("text", ["không có gì", "", None])
def test_no_legal_status(text: str | None) -> None:
    assert extract_legal_status(text) is None


DATA: dict[str, Any] = {
    "a": {"b": [{"c": 1}, {"c": 2}]},
    "empty": "",
    "none": None,
    "seller": {"full_name": "A"},
}


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("a.b[0].c", 1),
        ("a.b[1].c", 2),
        ("seller.full_name", "A"),
        ("empty, seller.full_name", "A"),  # an empty value falls through to the next candidate
        ("missing, none, seller.full_name", "A"),
    ],
)
def test_json_path(path: str, value: object) -> None:
    assert extract_by_json_path(DATA, path) == value


@pytest.mark.parametrize("path", ["a.b[5].c", "none", "missing", "", "a.b.c", "empty"])
def test_json_path_without_a_value(path: str) -> None:
    assert extract_by_json_path(DATA, path) is None


def test_json_path_of_nothing() -> None:
    assert extract_by_json_path(None, "a") is None
