"""Run GenericHtmlSpider offline against captured pages in tests/fixtures/html/."""

from collections.abc import Callable
from pathlib import Path

import httpx

from real_estate_price_tracking_systems.domain.entities import ParsedListingItem, RunMode
from real_estate_price_tracking_systems.infrastructure.config import load_site_config
from real_estate_price_tracking_systems.infrastructure.crawler.spiders import GenericHtmlSpider
from tests.unit.spiders.conftest import Handler

ROOT = Path(__file__).resolve().parents[3]
SITES_DIR = ROOT / "configs" / "sites"
HTML_DIR = ROOT / "tests" / "fixtures" / "html"
EMPTY_PAGE = "<html><body></body></html>"


def read(name: str) -> str:
    return (HTML_DIR / name).read_text(encoding="utf-8")


def html(text: str, status: int = 200) -> httpx.Response:
    return httpx.Response(status, text=text, headers={"content-type": "text/html; charset=utf-8"})


async def crawl_fixture(
    site_id: str, serve: Callable[[Handler], None]
) -> tuple[list[ParsedListingItem], GenericHtmlSpider]:
    """Crawl ``site_id`` with its production YAML.

    Page 1 is ``<site>_list.html`` and page 2 is empty (the end of the listings). The first
    card's detail URL serves ``<site>_detail.html``; every other detail URL is a 404, so the list
    data of those cards must still come through.
    """
    config = load_site_config(SITES_DIR / f"{site_id}.yaml")
    config = config.model_copy(
        update={"rate_limit": config.rate_limit.model_copy(update={"download_delay_sec": 0.001})}
    )
    list_html = read(f"{site_id}_list.html")
    detail_html = read(f"{site_id}_detail.html")
    spider = GenericHtmlSpider(config, retry_backoff_sec=0.001)

    first_page_url, _ = spider._build_page_url_and_params(config.pagination.start_page, 0)
    cards = spider._raw_items_from_page(list_html, first_page_url) or []
    detail_urls = [card["url"] for card in cards if "url" in card]
    list_pages_served = 0

    def handler(request: httpx.Request, proxy: str | None) -> httpx.Response:
        nonlocal list_pages_served
        url = str(request.url)
        if url in detail_urls:
            return html(detail_html) if url == detail_urls[0] else html("", 404)
        list_pages_served += 1
        return html(list_html if list_pages_served == 1 else EMPTY_PAGE)

    serve(handler)
    items = [item async for item, _raw in spider.crawl(RunMode.INCREMENTAL)]
    return items, spider
