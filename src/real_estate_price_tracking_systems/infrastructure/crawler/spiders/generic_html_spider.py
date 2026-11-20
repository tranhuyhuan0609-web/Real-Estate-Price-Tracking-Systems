"""Generic HTML spider: pagination, CSS/XPath/embedded-JSON extraction via parsel, detail pages."""

import asyncio
import json
import logging
import re
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from parsel import Selector

from real_estate_price_tracking_systems.application.ports import Spider
from real_estate_price_tracking_systems.domain.entities import (
    CrawlerConfig,
    ParsedListingItem,
    RunMode,
)
from real_estate_price_tracking_systems.infrastructure.crawler.http_clients import HttpClientPool
from real_estate_price_tracking_systems.infrastructure.crawler.parsing.json_path import (
    extract_by_json_path,
)
from real_estate_price_tracking_systems.infrastructure.crawler.parsing.listing_parser import (
    ListingParser,
)

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)
DEFAULT_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

# A comma separates fallback selectors, except inside brackets or parentheses (XPath, :not(a, b)).
_SELECTOR_SPLIT = re.compile(r",(?![^(\[]*[)\]])")


class GenericHtmlSpider(Spider):
    """Config-driven asynchronous spider for server-rendered HTML real estate sources.

    ``response_mapping.items_path`` selects the listing cards (CSS, XPath starting with ``/``, or
    ``json:<selector> -> <path>`` for JSON embedded in a script tag) and ``fields`` maps each
    listing field to a selector evaluated on the card. A field selector is one of:

    * CSS or XPath; ``::text`` selectors join their text nodes;
    * ``::attr(name)`` or ``@name`` to read an attribute of the card itself;
    * ``json:<selector> -> <path>``;
    * several of the above separated by commas, tried in order until one yields a value.

    How a crawl ended is reported like the API spider: ``aborted_reason`` for an error or a block
    (no usable response, an empty first page), ``exhausted`` only when a later page has no cards.
    With ``detail_page.enabled`` each card's own page is fetched (concurrently, bounded by
    ``concurrent_requests``) to fill what the list lacks, such as the phone, the date and the
    media. A detail link outside the feed's allowed domains is never requested: list pages carry
    ads that point to third-party sites. A detail page that fails leaves the list data in place.

    ``selector_errors``, ``detail_errors`` and ``parse_errors`` count fields, detail pages and
    items that failed without stopping the crawl; ``retry_backoff_sec`` is the base of the linear retry backoff.
    """

    def __init__(self, config: CrawlerConfig, retry_backoff_sec: float = 2.0) -> None:
        self.config = config
        self.parser = ListingParser(config)
        self.req_cfg = config.request
        self.page_cfg = config.pagination
        self.rate_cfg = config.rate_limit
        self.detail_cfg = config.detail_page
        self.retry_backoff_sec = retry_backoff_sec
        self.pages_crawled: int = 0
        self.aborted_reason: str | None = None
        self.exhausted: bool = False
        self.selector_errors: int = 0
        self.detail_errors: int = 0
        self.parse_errors: int = 0
        self._clients: HttpClientPool | None = None
        self._warned_selectors: set[str] = set()  # log each broken selector once per crawl

    # ------------------------------------------------------------------ selectors
    def _extract_selector_value(
        self, context: Selector, selector_str: str, is_list: bool = False
    ) -> Any:
        """Value of a (possibly comma-separated fallback) selector on ``context``."""
        if not selector_str:
            return None
        selector_str = selector_str.strip()

        if "," in selector_str and not selector_str.startswith("json:"):
            parts = [p.strip() for p in _SELECTOR_SPLIT.split(selector_str) if p.strip()]
            if len(parts) > 1:
                for part in parts:
                    value = self._extract_single_selector(context, part, is_list=is_list)
                    if value is not None and (not isinstance(value, str | list) or len(value) > 0):
                        return value
                return [] if is_list else None

        return self._extract_single_selector(context, selector_str, is_list=is_list)

    def _extract_single_selector(
        self, context: Selector, selector_str: str, is_list: bool = False
    ) -> Any:
        """One selector: ``json:<sel> -> <path>``, ``::attr(x)`` / ``@x`` on the node itself,
        XPath (``/``, ``./``) or CSS. Text selectors join their non-empty tokens."""
        try:
            if selector_str.startswith("json:"):
                return self._embedded_json(context, selector_str)
            own_attr = _own_attribute(selector_str)
            if own_attr is not None:
                value = _clean(context.attrib.get(own_attr))
                return [value] if is_list and value else value

            is_xpath = selector_str.startswith(("/", "./"))
            result = context.xpath(selector_str) if is_xpath else context.css(selector_str)
            tokens = [t.strip() for t in result.getall() if t and t.strip()]
            if is_list:
                return tokens or None
            if "::text" in selector_str or "text()" in selector_str:
                return " ".join(tokens) or None

            value = result.get()
            if value is None and "::attr(" in selector_str:
                # The card itself may be the element carrying the attribute.
                value = context.attrib.get(selector_str.split("::attr(")[-1].rstrip(")"))
            return _clean(value)
        except Exception as exc:
            # Broad on purpose: one bad field must not abort the crawl. But it must be visible,
            # because a broken selector looks exactly like "field not on the page".
            self.selector_errors += 1
            if selector_str not in self._warned_selectors:
                self._warned_selectors.add(selector_str)
                logger.warning(
                    "Site '%s': selector %r failed (%s: %s); the field is left empty.",
                    self.config.site_id,
                    selector_str,
                    type(exc).__name__,
                    exc,
                )
            return None

    def _embedded_json(self, context: Selector, selector_str: str) -> Any:
        """``json:<css_or_xpath> -> <json_path>``: read JSON from a script tag."""
        prefix, json_path = selector_str[5:].split("->", 1)
        script = self._extract_selector_value(context, prefix.strip())
        return extract_by_json_path(json.loads(script), json_path.strip()) if script else None

    # ------------------------------------------------------------------ requests
    async def _send_request(
        self, url: str, params: dict[str, Any] | None = None
    ) -> httpx.Response | None:
        """GET through the client pool, with retries (see ``HttpClientPool.request_with_retry``)."""
        assert self._clients is not None, "only called from crawl()"
        return await self._clients.request_with_retry(
            "GET",
            url,
            retries=self.rate_cfg.retry_times,
            backoff_sec=self.retry_backoff_sec,
            params=params,
            timeout=self.rate_cfg.timeout_sec,
        )

    def _build_page_url_and_params(
        self, current_page: int, current_offset: int
    ) -> tuple[str, dict[str, Any]]:
        """URL and query params of one list page.

        A ``{page}`` / ``{offset}`` placeholder in the configured URL is filled in; otherwise the
        page (or offset) goes in the query under ``page_param``.
        """
        base_url = (
            str(self.req_cfg.url)
            .replace("%7Bpage%7D", "{page}")
            .replace("%7Boffset%7D", "{offset}")
        )
        params: dict[str, Any] = dict(self.req_cfg.query_params)
        page_param = self.page_cfg.page_param
        limit_param = self.page_cfg.limit_param
        page_size = self.page_cfg.page_size

        if "{page}" in base_url or "{offset}" in base_url:
            return base_url.format(page=current_page, offset=current_offset), params
        params[page_param] = (
            current_offset if self.page_cfg.strategy == "offset_limit" else current_page
        )
        if limit_param:
            params[limit_param] = page_size
        return base_url, params

    def _headers(self) -> dict[str, str]:
        headers = dict(self.req_cfg.headers)
        headers.setdefault("User-Agent", DEFAULT_USER_AGENT)
        headers.setdefault("Accept", DEFAULT_ACCEPT)
        return headers

    # ------------------------------------------------------------------ crawl
    async def crawl(
        self, run_mode: RunMode = RunMode.INCREMENTAL
    ) -> AsyncGenerator[tuple[ParsedListingItem, dict[str, Any]]]:
        """Crawl list pages up to the page budget and yield ``(item, raw field dict)``."""
        self.pages_crawled = 0
        self.selector_errors = 0
        self.detail_errors = 0
        self.parse_errors = 0
        self.aborted_reason = None
        self.exhausted = False
        self._warned_selectors = set()
        max_pages = self.config.max_pages(run_mode)
        start_page = self.page_cfg.start_page
        logger.info(
            "Starting HTML crawl for site '%s' (mode: %s, max_pages: %d)",
            self.config.site_id,
            run_mode,
            max_pages,
        )

        detail_semaphore = asyncio.Semaphore(max(1, self.rate_cfg.concurrent_requests))

        async with HttpClientPool(
            self.config.proxy_settings, headers=self._headers(), follow_redirects=True
        ) as self._clients:
            current_page, current_offset = start_page, 0
            while self.pages_crawled < max_pages:
                url, params = self._build_page_url_and_params(current_page, current_offset)
                try:
                    response = await self._send_request(url, params=params or None)
                except httpx.HTTPError as exc:
                    self.aborted_reason = f"Network error at page {current_page}: {exc!r}"
                    break
                if response is None:
                    logger.warning("No response for %s. Stopping at page %d", url, current_page)
                    self.aborted_reason = (
                        f"No usable HTTP response at page {current_page} (blocked or server error)"
                    )
                    break
                self.pages_crawled += 1

                raw_items = self._raw_items_from_page(response.text, str(response.url))
                if raw_items is None:  # no card matched
                    if current_page == start_page:
                        # An empty first page is a layout change or a block, not the end.
                        self.aborted_reason = (
                            f"No items matched '{self.config.response_mapping.items_path}' on "
                            "first page; possible layout change or bot block"
                        )
                    else:
                        self.exhausted = True
                    break

                if self.detail_cfg.enabled:
                    await asyncio.gather(
                        *(self._enrich_from_detail(item, detail_semaphore) for item in raw_items)
                    )
                for raw_item in raw_items:
                    parsed = self._parse(raw_item)
                    if parsed is not None:
                        yield parsed, raw_item

                current_page += 1
                current_offset += self.page_cfg.page_size
                if self.rate_cfg.download_delay_sec > 0:
                    await asyncio.sleep(self.rate_cfg.download_delay_sec)

    # ------------------------------------------------------------------ crawl steps
    def _cards(self, selector: Selector) -> tuple[list[Any], bool]:
        """Listing cards on a page, and whether they are embedded-JSON dicts."""
        items_path = self.config.response_mapping.items_path
        if items_path.startswith("json:"):
            prefix, json_path = items_path[5:].split("->", 1)
            script = self._extract_selector_value(selector, prefix.strip())
            if script:
                try:
                    found = extract_by_json_path(json.loads(script), json_path.strip())
                    if isinstance(found, list):
                        return found, True
                except ValueError as exc:
                    logger.error("Error parsing embedded JSON feed: %s", exc)
            return [], True
        if items_path.startswith(("/", "./")):
            return list(selector.xpath(items_path)), False
        return list(selector.css(items_path)), False

    def _raw_items_from_page(self, html: str, page_url: str) -> list[dict[str, Any]] | None:
        """Raw field dicts of the cards that carry an id or URL; None when no card matched."""
        cards, is_json = self._cards(Selector(text=html))
        if not cards:
            logger.info(
                "No items matched selector '%s'. Reached end of listings.",
                self.config.response_mapping.items_path,
            )
            return None
        items: list[dict[str, Any]] = []
        for card in cards:
            raw: dict[str, Any] = {}
            for field, path in self.config.response_mapping.fields.items():
                if is_json and isinstance(card, dict):
                    value = extract_by_json_path(card, path)
                else:
                    value = self._extract_selector_value(card, path, is_list=field == "media_list")
                if value is None:
                    continue
                if (
                    field in ("url", "thumbnail_url")
                    and isinstance(value, str)
                    and not value.startswith("http")
                ):
                    value = urljoin(page_url, value)
                raw[field] = value
            if raw.get("external_id") or raw.get("external_code") or raw.get("url"):
                items.append(raw)
        return items

    def _is_allowed_url(self, url: str) -> bool:
        host = urlsplit(url).hostname
        return not host or self.config.is_allowed_domain(host)

    async def _enrich_from_detail(self, item: dict[str, Any], semaphore: asyncio.Semaphore) -> None:
        """Fill ``item`` with the detail page's fields. Off-domain links are never fetched."""
        detail_url = item.get(self.detail_cfg.url_field) or item.get("url")
        if not detail_url or not self._is_allowed_url(detail_url):
            return
        async with semaphore:
            try:
                if self.rate_cfg.download_delay_sec > 0:
                    await asyncio.sleep(self.rate_cfg.download_delay_sec)
                response = await self._send_request(detail_url)
            except httpx.HTTPError as exc:
                self.detail_errors += 1
                logger.warning(
                    "Site '%s': detail page %s failed (%s: %s); phone, date and media may be missing.",
                    self.config.site_id,
                    detail_url,
                    type(exc).__name__,
                    exc,
                )
                return
        if response is None:
            self.detail_errors += 1
            logger.warning(
                "Site '%s': detail page %s returned no usable response.",
                self.config.site_id,
                detail_url,
            )
            return
        page = Selector(text=response.text)
        for field, path in self.detail_cfg.fields.items():
            is_list = field == "media_list"
            value = self._extract_selector_value(page, path, is_list=is_list)
            if value is None:
                continue
            item[field] = (
                [urljoin(detail_url, u) for u in value]
                if is_list and isinstance(value, list)
                else value
            )

    def _parse(self, raw_item: dict[str, Any]) -> ParsedListingItem | None:
        try:
            parsed = self.parser.parse_item(raw_item)
        except Exception:
            # One malformed item must not stop the crawl; it is counted and logged.
            self.parse_errors += 1
            logger.error(
                "Site '%s': could not parse listing item", self.config.site_id, exc_info=True
            )
            return None
        if parsed.details.url and not self._is_allowed_url(parsed.details.url):
            logger.warning(
                "Listing host '%s' not allowed. Skipping item.",
                urlsplit(parsed.details.url).hostname,
            )
            return None
        return parsed


def _own_attribute(selector: str) -> str | None:
    """Attribute name for "::attr(name)" / "@name", which read the context node itself."""
    if selector.startswith("::attr(") and selector.endswith(")"):
        return selector[7:-1]
    if selector.startswith("@"):
        return selector[1:]
    return None


def _clean(value: str | None) -> str | None:
    return value.strip() if value and value.strip() else None
