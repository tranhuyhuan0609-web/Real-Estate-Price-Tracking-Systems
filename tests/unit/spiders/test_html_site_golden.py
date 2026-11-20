"""Golden tests: production YAML configs + GenericHtmlSpider against captured, anonymised pages.

A failure here after changing a selector means the config no longer reads the real layout. When a
site changes its layout, re-capture with ``scripts/capture_site_fixture.py`` and update EXPECTED.
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from tests.unit.spiders.conftest import Handler
from tests.unit.spiders.html_golden_harness import HTML_DIR, crawl_fixture

VN = ZoneInfo("Asia/Ho_Chi_Minh")  # content_timezone: dates on the page are local midnight

# (listing_key, area_m2, price_vnd) of every card, in page order
EXPECTED = {
    "mogi": [
        ("mogi_22751689", 91.0, 83_000_000_000),
        ("mogi_22595305", 250.0, 53_000_000_000),
        ("mogi_22599559", 284.0, 32_000_000_000),
    ],
    "homedy": [
        ("homedy_3225661", 114.0, 9_800_000_000),
        ("homedy_1490980", 59.0, 2_390_000_000),
    ],
    "cafeland": [
        ("cafeland_3195376", 108.0, 8_800_000_000),
        ("cafeland_3176122", 108.0, 8_900_000_000),
        ("cafeland_3194057", 264.0, 8_800_000_000),
    ],
}

# Fields that only the detail page provides (first card only)
EXPECTED_DETAIL: dict[str, dict[str, Any]] = {
    "mogi": {
        "published_at": datetime(2026, 11, 4, tzinfo=VN),
        "phone": "0900000001",
        "media_min": 10,
        "city": "Thành phố Hồ Chí Minh",
        "district": "Quận 1",
    },
    "homedy": {
        "published_at": datetime(2026, 11, 2, tzinfo=VN),
        "phone": "0900000001",
        "media_min": 0,
        "city": "Thành phố Đà Nẵng",
        "district": "Quận Sơn Trà",
    },
    "cafeland": {
        "published_at": datetime(2026, 11, 3, tzinfo=VN),
        "phone": "0900000007",
        "media_min": 0,
        "city": "Thành phố Cần Thơ",
        "district": "Cái Răng",
    },
}


@pytest.mark.parametrize("site_id", sorted(EXPECTED))
async def test_list_page_cards(site_id: str, serve: Callable[[Handler], None]) -> None:
    items, spider = await crawl_fixture(site_id, serve)

    assert [(i.listing_key, i.area_m2, i.current_price_vnd) for i in items] == EXPECTED[site_id]
    assert spider.exhausted and spider.aborted_reason is None  # empty page 2 = clean end
    assert spider.selector_errors == 0 and spider.parse_errors == 0
    for item in items:
        assert item.source == site_id
        assert item.details.url.startswith("https://")
        assert item.details.title


@pytest.mark.parametrize("site_id", sorted(EXPECTED_DETAIL))
async def test_detail_page_enrichment(site_id: str, serve: Callable[[Handler], None]) -> None:
    items, spider = await crawl_fixture(site_id, serve)
    first, want = items[0], EXPECTED_DETAIL[site_id]

    assert first.published_at == want["published_at"].astimezone(UTC)
    assert first.advertiser is not None and first.advertiser.phone == want["phone"]
    assert len(first.details.media_list or []) >= want["media_min"]
    assert (first.details.city_name, first.details.district_name) == (
        want["city"],
        want["district"],
    )
    # the other cards' detail pages 404: their list data is kept, and each failure is counted
    assert spider.detail_errors == len(items) - 1
    assert all(item.current_price_vnd for item in items)


@pytest.mark.parametrize("site_id", sorted(EXPECTED))
def test_fixtures_hold_no_real_contact_data(site_id: str) -> None:
    """Every phone and e-mail in a captured page must be a fake from the reserved range."""
    for kind in ("list", "detail"):
        text = (HTML_DIR / f"{site_id}_{kind}.html").read_text(encoding="utf-8")
        emails = set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.-]+", text))
        assert all(e.endswith("@example.com") for e in emails), emails
        phones = set(re.findall(r"(?<!\d)0[35789](?:[\s.]?\d){8}(?!\d)", text))
        real = {p for p in phones if not re.sub(r"\D", "", p).startswith("0900000")}
        # long digit runs are image names or timestamps; a *phone-shaped* run is what matters
        assert not {p for p in real if len(re.sub(r"\D", "", p)) == 10}, real
