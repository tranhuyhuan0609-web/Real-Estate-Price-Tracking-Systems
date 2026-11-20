"""GenericHtmlSpider on small synthetic pages, driven through httpx's MockTransport."""

import asyncio
import copy
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from parsel import Selector

from real_estate_price_tracking_systems.domain.entities import CrawlerConfig
from real_estate_price_tracking_systems.infrastructure.crawler.spiders import (
    GenericHtmlSpider,
    create_spider,
)
from tests.unit.spiders.conftest import Handler

LIST_HTML = """
<html><body>
  <div class="props-item" data-id="101">
    <h2 class="prop-title"><a href="/quan-1/ban-nha-pho/nha-dep-id101">Nhà đẹp mặt tiền Quận 1</a></h2>
    <span class="price">5,2 tỷ</span>
    <span class="square">100 m²</span>
    <div class="prop-addr">Phường Bến Nghé, Quận 1, TP Hồ Chí Minh</div>
    <img class="thumb" src="/images/thumb101.jpg" />
  </div>
  <div class="props-item" data-id="102">
    <h2 class="prop-title"><a href="/quan-2/ban-dat/dat-nen-id102">Đất nền An Phú</a></h2>
    <span class="price">45 tr/m²</span>
    <span class="square">80 m²</span>
    <div class="prop-addr">Phường An Phú, Quận 2, TP Hồ Chí Minh</div>
    <img class="thumb" src="/images/thumb102.jpg" />
  </div>
</body></html>
"""

DETAIL_HTML = """
<html><body>
  <div class="agent-name"><a href="/moi-gioi/0912345678-nguyen-van-a-uid888">Nguyễn Văn A</a></div>
  <div class="property-description">Nhà chính chủ, sổ hồng riêng, đường trước nhà 6m.</div>
  <div class="media-gallery"><img src="/photos/photo1.jpg" /><img src="/photos/photo2.jpg" /></div>
</body></html>
"""

EMPTY = "<html><body></body></html>"


def base_data() -> dict[str, Any]:
    return {
        "site_id": "mogi",
        "name": "Mogi",
        "crawler_type": "html",
        "interval_seconds": 300,
        "request": {"url": "https://mogi.vn/mua-nha-dat", "headers": {"User-Agent": "TestBot"}},
        "pagination": {
            "page_param": "cp",
            "max_pages_incremental": 3,
            "max_pages_full_sweep": 5,
        },
        "rate_limit": {"download_delay_sec": 0.001, "retry_times": 1, "timeout_sec": 5},
        "response_mapping": {
            "items_path": "div.props-item",
            "fields": {
                "external_id": "div.props-item::attr(data-id)",
                "url": "h2.prop-title a::attr(href)",
                "title": "h2.prop-title a::text",
                "price_vnd": "span.price::text",
                "area_m2": "span.square::text",
                "city_name": "div.prop-addr::text",
                "thumbnail_url": "img.thumb::attr(src)",
            },
        },
        "detail_page": {
            "enabled": True,
            "fields": {
                "advertiser_phone": "div.agent-name a::attr(href)",
                "advertiser_name": "div.agent-name a::text",
                "description": "div.property-description::text",
                "media_list": "div.media-gallery img::attr(src)",
            },
        },
    }


def make_config(**overrides: Any) -> CrawlerConfig:
    data = copy.deepcopy(base_data())
    for key, value in overrides.items():
        data[key] = {**data[key], **value} if isinstance(value, dict) else value
    return CrawlerConfig.model_validate(data)


def html(text: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, text=text, headers={"content-type": "text/html; charset=utf-8"})


def site(pages: dict[str, str]) -> Handler:
    """Serve ``pages`` by URL path; list pages by their ``cp`` parameter; unknown paths 404."""

    def handler(request: httpx.Request, proxy: str | None) -> httpx.Response:
        if request.url.path == "/mua-nha-dat":
            return html(LIST_HTML if request.url.params.get("cp") == "1" else EMPTY)
        body = pages.get(request.url.path)
        return html(body) if body is not None else html("not found", 404)

    return handler


DETAIL_PAGES = {
    "/quan-1/ban-nha-pho/nha-dep-id101": DETAIL_HTML,
    "/quan-2/ban-dat/dat-nen-id102": DETAIL_HTML,
}


async def crawl(spider: GenericHtmlSpider) -> list[Any]:
    return [item async for item, _raw in spider.crawl()]


# --- list pages, detail pages, ending --------------------------------------------------------


async def test_crawl_with_detail_pages(serve: Callable[[Handler], None]) -> None:
    serve(site(DETAIL_PAGES))
    spider = GenericHtmlSpider(make_config(), retry_backoff_sec=0.001)

    items = await crawl(spider)

    first, second = items
    assert first.listing_key == "mogi_101"
    assert first.details.title == "Nhà đẹp mặt tiền Quận 1"
    assert (first.current_price_vnd, first.area_m2) == (5_200_000_000, 100.0)
    assert first.current_price_per_m2 == 52_000_000
    assert first.details.url == "https://mogi.vn/quan-1/ban-nha-pho/nha-dep-id101"
    assert first.details.thumbnail_url == "https://mogi.vn/images/thumb101.jpg"
    # filled from the detail page
    assert first.advertiser is not None
    assert (first.advertiser.phone, first.advertiser.name) == ("0912345678", "Nguyễn Văn A")
    assert first.advertiser.advertiser_id == "adv_mogi_0912345678"
    assert first.details.legal_status == "Sổ đỏ/hồng"
    assert first.details.media_list == [
        "https://mogi.vn/photos/photo1.jpg",
        "https://mogi.vn/photos/photo2.jpg",
    ]
    # a per-m2 price on the card yields the total from the area
    assert (second.current_price_per_m2, second.current_price_vnd) == (45_000_000, 3_600_000_000)
    assert spider.exhausted and spider.aborted_reason is None
    assert spider.pages_crawled == 2  # page 1 and the empty page 2


async def test_without_detail_pages_none_are_fetched(
    serve: Callable[[Handler], None], requests_seen: list[Any]
) -> None:
    serve(site(DETAIL_PAGES))
    spider = GenericHtmlSpider(make_config(detail_page={"enabled": False}), retry_backoff_sec=0.001)

    items = await crawl(spider)

    assert len(items) == 2 and items[0].advertiser is not None
    assert items[0].advertiser.phone is None
    assert {r.url.path for r, _ in requests_seen} == {"/mua-nha-dat"}


async def test_a_failing_detail_page_keeps_the_list_data(serve: Callable[[Handler], None]) -> None:
    serve(site({"/quan-1/ban-nha-pho/nha-dep-id101": DETAIL_HTML}))  # the other one 404s
    spider = GenericHtmlSpider(make_config(), retry_backoff_sec=0.001)

    first, second = await crawl(spider)

    assert first.advertiser is not None and first.advertiser.phone == "0912345678"
    assert second.listing_key == "mogi_102" and second.current_price_vnd == 3_600_000_000
    assert second.advertiser is not None and second.advertiser.phone is None
    assert spider.detail_errors == 1 and spider.aborted_reason is None


async def test_an_empty_first_page_is_an_abort(serve: Callable[[Handler], None]) -> None:
    serve(lambda request, proxy: html(EMPTY))
    spider = GenericHtmlSpider(make_config(), retry_backoff_sec=0.001)

    assert await crawl(spider) == []
    assert spider.exhausted is False
    assert spider.aborted_reason is not None and "first page" in spider.aborted_reason


async def test_a_blocked_list_page_aborts(
    serve: Callable[[Handler], None], requests_seen: list[Any]
) -> None:
    serve(lambda request, proxy: html("blocked", 403))
    spider = GenericHtmlSpider(make_config(), retry_backoff_sec=0.001)

    assert await crawl(spider) == []
    assert len(requests_seen) == 1  # a 403 is not retried
    assert spider.aborted_reason is not None and not spider.exhausted


async def test_a_network_error_aborts_without_raising(
    serve: Callable[[Handler], None], requests_seen: list[Any]
) -> None:
    def handler(request: httpx.Request, proxy: str | None) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    serve(handler)
    spider = GenericHtmlSpider(make_config(), retry_backoff_sec=0.001)

    assert await crawl(spider) == []
    assert len(requests_seen) == 2  # retry_times=1
    assert spider.aborted_reason is not None and "Network error" in spider.aborted_reason


async def test_pagination_goes_in_the_query_and_stops_at_the_budget(
    serve: Callable[[Handler], None], requests_seen: list[Any]
) -> None:
    serve(lambda request, proxy: html(LIST_HTML))  # every page has cards
    config = make_config(pagination={"max_pages_incremental": 2}, detail_page={"enabled": False})
    spider = GenericHtmlSpider(config, retry_backoff_sec=0.001)

    await crawl(spider)

    pages = [dict(r.url.params) for r, _ in requests_seen]
    assert [p["cp"] for p in pages] == ["1", "2"]
    assert (spider.pages_crawled, spider.exhausted, spider.aborted_reason) == (2, False, None)


async def test_page_placeholder_in_the_url(
    serve: Callable[[Handler], None], requests_seen: list[Any]
) -> None:
    config = make_config(
        request={"url": "https://mogi.vn/ban-nha-dat/p{page}"}, detail_page={"enabled": False}
    )
    serve(lambda request, proxy: html(LIST_HTML if request.url.path.endswith("p1") else EMPTY))
    spider = GenericHtmlSpider(config, retry_backoff_sec=0.001)

    await crawl(spider)

    assert [r.url.path for r, _ in requests_seen] == ["/ban-nha-dat/p1", "/ban-nha-dat/p2"]
    assert spider.exhausted


async def test_default_browser_headers(
    serve: Callable[[Handler], None], requests_seen: list[Any]
) -> None:
    serve(lambda request, proxy: html(EMPTY))
    config = make_config(request={"headers": {}})
    await crawl(GenericHtmlSpider(config, retry_backoff_sec=0.001))

    headers = requests_seen[0][0].headers
    assert "Chrome" in headers["user-agent"] and "text/html" in headers["accept"]


# --- never fetch off-domain detail links -----------------------------------------------------


async def test_off_domain_detail_links_are_never_fetched(
    serve: Callable[[Handler], None], requests_seen: list[Any]
) -> None:
    """Ad cards link to third-party hosts; checking the allow-list only after parsing would
    still have requested those pages."""
    ad_card = LIST_HTML.replace(
        "/quan-2/ban-dat/dat-nen-id102", "https://ads.example.net/landing?id=102"
    )

    def handler(request: httpx.Request, proxy: str | None) -> httpx.Response:
        if request.url.host == "mogi.vn" and request.url.path == "/mua-nha-dat":
            return html(ad_card if request.url.params.get("cp") == "1" else EMPTY)
        return html(DETAIL_HTML)

    serve(handler)
    spider = GenericHtmlSpider(make_config(), retry_backoff_sec=0.001)

    items = await crawl(spider)

    assert {r.url.host for r, _ in requests_seen} == {"mogi.vn"}
    assert [i.listing_key for i in items] == ["mogi_101"]  # the ad itself is skipped too


async def test_enrichment_leaves_an_off_domain_item_untouched() -> None:
    spider = GenericHtmlSpider(make_config())
    item = {"url": "https://ads.example.net/landing"}

    await spider._enrich_from_detail(item, asyncio.Semaphore(1))

    assert item == {"url": "https://ads.example.net/landing"}


# --- selectors -------------------------------------------------------------------------------


def spider() -> GenericHtmlSpider:
    return GenericHtmlSpider(make_config())


def test_comma_separated_selectors_are_fallbacks() -> None:
    page = Selector(text='<div><span class="b">B</span></div>')
    assert spider()._extract_selector_value(page, "span.a::text, span.b::text") == "B"
    assert spider()._extract_selector_value(page, "span.a::text, span.c::text") is None


def test_a_comma_inside_xpath_brackets_is_not_a_separator() -> None:
    page = Selector(
        text=(
            '<div class="info-attr"><span>Ngày đăng</span><span>31/10/2026</span></div>'
            '<span class="fallback-date">01/01/2026</span>'
        )
    )
    selector = (
        "//div[contains(@class, 'info-attr')][span[contains(text(), 'Ngày đăng')]]/span[2]/text(), "
        "span.fallback-date::text"
    )
    assert spider()._extract_selector_value(page, selector) == "31/10/2026"


def test_attribute_of_the_card_itself() -> None:
    card = Selector(text='<div class="props-item" data-id="7"><b>x</b></div>').css("div")[0]
    assert spider()._extract_selector_value(card, "div.props-item::attr(data-id)") == "7"
    assert spider()._extract_selector_value(card, "@data-id") == "7"
    assert spider()._extract_selector_value(card, "::attr(data-id)") == "7"


def test_text_nodes_are_joined_and_lists_returned_whole() -> None:
    page = Selector(text='<p class="x">a <b> b </b> c</p><img src="1"><img src="2">')
    s = spider()
    assert s._extract_selector_value(page, "p.x *::text, p.x::text") is not None
    assert s._extract_selector_value(page, "img::attr(src)", is_list=True) == ["1", "2"]


def test_embedded_json_selector() -> None:
    page = Selector(text='<script id="d">{"a": {"b": [{"c": 5}]}}</script>')
    assert spider()._extract_selector_value(page, "json:script#d::text -> a.b[0].c") == 5


async def test_embedded_json_cards(serve: Callable[[Handler], None]) -> None:
    page = (
        '<script id="data">{"props": {"items": ['
        '{"id": 11, "link": "/d/11", "name": "Nhà A", "gia": "3 tỷ", "dt": "60 m2"},'
        '{"id": 12, "link": "/d/12", "name": "Nhà B", "gia": "4 tỷ", "dt": "80 m2"}'
        "]}}</script>"
    )
    config = make_config(
        response_mapping={
            "items_path": "json:script#data::text -> props.items",
            "fields": {
                "external_id": "id",
                "url": "link",
                "title": "name",
                "price_vnd": "gia",
                "area_m2": "dt",
            },
        },
        detail_page={"enabled": False},
    )
    serve(lambda request, proxy: html(page if request.url.params.get("cp") == "1" else EMPTY))
    spider_ = GenericHtmlSpider(config, retry_backoff_sec=0.001)

    items = await crawl(spider_)

    assert [(i.listing_key, i.current_price_vnd) for i in items] == [
        ("mogi_11", 3_000_000_000),
        ("mogi_12", 4_000_000_000),
    ]


def test_a_broken_selector_is_counted_and_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    s = spider()
    page = Selector(text="<html><body><p>x</p></body></html>")

    with caplog.at_level("WARNING"):
        for _ in range(3):
            assert s._extract_single_selector(page, "//p[") is None  # invalid XPath

    assert s.selector_errors == 3
    assert sum("selector '//p['" in r.getMessage() for r in caplog.records) == 1


# --- factory ---------------------------------------------------------------------------------


def test_factory_creates_the_html_spider() -> None:
    assert isinstance(create_spider(make_config()), GenericHtmlSpider)
