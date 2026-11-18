"""Golden test: a captured, anonymised Meeyland API item parsed with the production YAML config.

The fixture keeps the structure of a real response, so a change to the parser or to
``configs/sites/meeyland.yaml`` that alters what is extracted fails here. Seller name, phone and
e-mail are fake; the fixture must never contain real personal data.
"""

import re
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from real_estate_price_tracking_systems.domain.entities import (
    AdvertiserKind,
    Category,
    PropertyType,
)
from real_estate_price_tracking_systems.infrastructure.config import load_site_config
from real_estate_price_tracking_systems.infrastructure.crawler.parsing.listing_parser import (
    ListingParser,
    infer_city,
)
from tests.unit.parsers.conftest import FIXTURES_DIR, SITES_DIR, load_fixture


@pytest.fixture
def parser() -> ListingParser:
    return ListingParser(load_site_config(SITES_DIR / "meeyland.yaml"))


@pytest.fixture
def raw() -> dict[str, Any]:
    item: dict[str, Any] = load_fixture("meeyland_item.json")
    return item


def test_parse_captured_meeyland_item(parser: ListingParser, raw: dict[str, Any]) -> None:
    item = parser.parse_item(raw)

    assert item.listing_key == "meeyland_307624752"
    assert (item.source, item.external_code) == ("meeyland", 307624752)
    assert item.category is Category.SALE
    assert item.property_type is PropertyType.LAND
    assert (item.area_m2, item.facade_m, item.depth_m) == (80.0, 5.0, 16.0)
    assert item.current_price_vnd == 1_850_000_000
    assert item.current_price_per_m2 == 23_125_000
    assert item.published_at == datetime(2026, 10, 12, 9, 5, 28, 363000, tzinfo=UTC)

    d = item.details
    assert d.url == "https://meeyland.com/ban-dat-can-giuoc-tay-ninh-p1122/307624752"
    assert (d.city_name, d.district_name, d.ward_name) == (
        "Tỉnh Tây Ninh",
        "Cần Giuộc",
        "Xã Cần Giuộc",
    )
    assert d.legal_status == "Sổ đỏ/hồng"
    assert d.lat is not None and d.lng is not None
    assert 8 < d.lat < 24 and 102 < d.lng < 110
    assert d.media_list and all(url.startswith("https://") for url in d.media_list)

    advertiser = item.advertiser
    assert advertiser is not None
    assert advertiser.phone == "0900000001"
    assert advertiser.advertiser_id == "adv_meeyland_0900000001"
    assert advertiser.kind is AdvertiserKind.BROKER
    assert advertiser.is_verified is True


def test_parsing_is_deterministic(parser: ListingParser, raw: dict[str, Any]) -> None:
    """The fingerprint and keys must not depend on anything but the item."""
    assert parser.parse_item(raw) == parser.parse_item(raw)


def test_fixture_holds_no_personal_data() -> None:
    """Seller contact must be fake: example.com e-mails and a reserved 0900000xxx phone."""
    text = (FIXTURES_DIR / "meeyland_item.json").read_text(encoding="utf-8")
    emails = set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text))
    assert emails and all(email.endswith("@example.com") for email in emails)
    phones = set(re.findall(r"\b0[35789]\d[\d.\s]{7,9}\d\b", text))
    assert all(re.sub(r"\D", "", phone).startswith("0900000") for phone in phones)


# --- url handling ---------------------------------------------------------------------------


def test_url_template_is_used_when_the_item_has_no_url(raw: dict[str, Any]) -> None:
    config = load_site_config(SITES_DIR / "meeyland.yaml")
    mapping = config.response_mapping.model_copy(
        update={"url_template": "https://x.vn/{external_code}.htm"}
    )
    parser = ListingParser(config.model_copy(update={"response_mapping": mapping}))
    raw = {k: v for k, v in raw.items() if k != "url"}

    assert parser.parse_item(raw).details.url == "https://x.vn/307624752.htm"


def test_the_items_own_url_beats_the_template(raw: dict[str, Any]) -> None:
    config = load_site_config(SITES_DIR / "meeyland.yaml")
    mapping = config.response_mapping.model_copy(
        update={"url_template": "https://x.vn/{external_id}"}
    )
    parser = ListingParser(config.model_copy(update={"response_mapping": mapping}))

    assert parser.parse_item(raw).details.url.startswith("https://meeyland.com/")


def test_an_item_without_any_url_is_rejected(parser: ListingParser, raw: dict[str, Any]) -> None:
    raw = {k: v for k, v in raw.items() if k != "url"}
    with pytest.raises(ValidationError, match="url"):
        parser.parse_item(raw)


# --- city inference -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "district", "city"),
    [
        ("https://x.vn/ban-nha-ha-noi/1", None, "Thành phố Hà Nội"),
        ("https://x.vn/ho-chi-minh/1", "Quận 1", "Thành phố Hồ Chí Minh"),  # the URL wins
        ("https://x.vn/ban-nha/1", "Quận 7", "Thành phố Hồ Chí Minh"),
        ("https://x.vn/da-nang/1", None, "Thành phố Đà Nẵng"),
        ("https://x.vn/ban-nha/1", "Cầu Giấy", "Thành phố Hà Nội"),
        ("https://x.vn/ban-nha/1", None, None),
        ("", "", None),
    ],
)
def test_infer_city(url: str, district: str | None, city: str | None) -> None:
    assert infer_city(url, district) == city
