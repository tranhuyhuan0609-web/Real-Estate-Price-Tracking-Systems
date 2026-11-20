"""Generic REST API spider: pagination, retries, rate limiting, domain allow-list, mapping."""

import asyncio
import copy
import logging
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import urlsplit

import httpx

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

RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})
DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) RealEstateBot/1.0"


class GenericApiSpider(Spider):
    """Config-driven asynchronous spider for REST API real estate sources.

    How a crawl ended is reported in two attributes that the crawl use case reads:

    * ``aborted_reason``: set when the crawl stopped because of an error or a block (no usable
      response, invalid JSON, an empty first page, a missing items path).
    * ``exhausted``: True only when a page after the first came back empty, i.e. the end of the
      listings was really reached. Stopping at the page budget sets neither.

    ``retry_backoff_sec`` is the base of the linear backoff between retries (attempt n waits
    ``n * retry_backoff_sec``); tests pass a tiny value.
    """

    def __init__(self, config: CrawlerConfig, retry_backoff_sec: float = 2.0) -> None:
        self.config = config
        self.parser = ListingParser(config)
        self.req_cfg = config.request
        self.page_cfg = config.pagination
        self.rate_cfg = config.rate_limit
        self.retry_backoff_sec = retry_backoff_sec
        self.pages_crawled: int = 0
        self.aborted_reason: str | None = None
        self.exhausted: bool = False
        self.parse_errors: int = 0
        self._semaphore = asyncio.Semaphore(self.rate_cfg.concurrent_requests)
        self._clients: HttpClientPool | None = None

    async def _send_request_with_retry(
        self,
        url: str,
        method: str,
        headers: dict[str, str],
        params: dict[str, Any],
        json_body: dict[str, Any] | None,
    ) -> httpx.Response | None:
        """One page request. Retries 429/5xx and network errors with backoff.

        Returns the 200 response, or None for a non-retryable status or when retries ran out.
        The last network error is re-raised so the caller can say what went wrong.
        """
        assert self._clients is not None, "only called from crawl()"
        retries = self.rate_cfg.retry_times

        for attempt in range(1 + retries):
            client = self._clients.next()  # moves to the next proxy when rotating
            try:
                async with self._semaphore:
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        params=params,
                        json=json_body,
                        timeout=self.rate_cfg.timeout_sec,
                    )
            except httpx.HTTPError as exc:  # network errors and timeouts
                self._clients.record_failure(client)
                logger.warning(
                    "Attempt %d/%d network error for %s: %s", attempt + 1, retries + 1, url, exc
                )
                if attempt == retries:
                    raise
                await asyncio.sleep(self.retry_backoff_sec * (attempt + 1))
                continue

            if response.status_code == 200:
                self._clients.record_success(client)
                return response
            if response.status_code in RETRYABLE_STATUSES:
                self._clients.record_failure(client)
                logger.warning(
                    "Attempt %d/%d for %s received status %d. Backing off...",
                    attempt + 1,
                    retries + 1,
                    url,
                    response.status_code,
                )
                if attempt < retries:
                    await asyncio.sleep(self.retry_backoff_sec * (attempt + 1))
                continue
            logger.error("HTTP error %d for URL: %s", response.status_code, url)
            return None
        return None

    async def crawl(
        self, run_mode: RunMode = RunMode.INCREMENTAL
    ) -> AsyncGenerator[tuple[ParsedListingItem, dict[str, Any]]]:
        """Crawl pages up to the page budget of ``run_mode`` and yield ``(item, raw payload)``."""
        self.pages_crawled = 0
        self.parse_errors = 0
        self.aborted_reason = None
        self.exhausted = False
        max_pages = self.config.max_pages(run_mode)
        logger.info(
            "Starting crawl for site '%s' (mode: %s, max_pages: %d)",
            self.config.site_id,
            run_mode,
            max_pages,
        )
        headers = dict(self.req_cfg.headers)
        headers.setdefault("User-Agent", DEFAULT_USER_AGENT)

        async with HttpClientPool(
            self.config.proxy_settings, headers=headers, follow_redirects=True
        ) as self._clients:
            current_page = self.page_cfg.start_page
            while self.pages_crawled < max_pages:
                params, body = self._page_request(current_page)
                try:
                    response = await self._send_request_with_retry(
                        url=str(self.req_cfg.url),
                        method=self.req_cfg.method,
                        headers=headers,
                        params=params,
                        json_body=body,
                    )
                except httpx.HTTPError as exc:
                    self.aborted_reason = f"Network error at page {current_page}: {exc!r}"
                    break
                if response is None:
                    logger.warning("No usable response. Stopping crawl at page %d", current_page)
                    self.aborted_reason = (
                        f"No usable HTTP response at page {current_page} (blocked or server error)"
                    )
                    break
                try:
                    payload = response.json()
                except ValueError as exc:
                    logger.error("Invalid JSON on page %d: %s", current_page, exc)
                    self.aborted_reason = f"Invalid JSON response at page {current_page}: {exc}"
                    break
                self.pages_crawled += 1

                items = self._page_items(payload, current_page)
                if items is None:
                    break
                for raw_item in items:
                    parsed = self._parse(raw_item) if isinstance(raw_item, dict) else None
                    if parsed is not None:
                        yield parsed, raw_item

                current_page += 1
                if self.rate_cfg.download_delay_sec > 0:
                    await asyncio.sleep(self.rate_cfg.download_delay_sec)

    # ------------------------------------------------------------------ crawl steps
    def _page_request(self, page: int) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Query params and JSON body (POST only) for one page."""
        params: dict[str, Any] = dict(self.req_cfg.query_params)
        body: dict[str, Any] = (
            copy.deepcopy(self.req_cfg.body_template) if self.req_cfg.body_template else {}
        )
        page_size = self.page_cfg.page_size
        if self.page_cfg.strategy == "offset_limit":
            value = (page - self.page_cfg.start_page) * page_size
        else:
            value = page
        target = body if self.page_cfg.param_location == "body" else params
        target[self.page_cfg.page_param] = value
        if self.page_cfg.limit_param:
            target[self.page_cfg.limit_param] = page_size
        return params, body if self.req_cfg.method == "POST" else None

    def _page_items(self, payload: Any, page: int) -> list[Any] | None:
        """Items of a page, or None to stop: end of listings (exhausted) or a broken page (aborted)."""
        stop_path = self.config.items_stop_path
        stop_items = extract_by_json_path(payload, stop_path)
        if not stop_items or not isinstance(stop_items, list):
            logger.info("No items at '%s' on page %d: end of listings.", stop_path, page)
            if page == self.page_cfg.start_page:
                # An empty first page is an API change or a block, not the end of the listings.
                self.aborted_reason = (
                    f"No items on first page (stop path '{stop_path}'); "
                    "possible API change or bot block"
                )
            else:
                self.exhausted = True
            return None
        items_path = self.config.response_mapping.items_path
        items = stop_items if items_path == stop_path else extract_by_json_path(payload, items_path)
        if not items or not isinstance(items, list):
            logger.error("Items path '%s' missing or not a list at page %d", items_path, page)
            self.aborted_reason = f"Items path '{items_path}' missing or not a list at page {page}"
            return None
        return items

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
        host = urlsplit(parsed.details.url).hostname if parsed.details.url else None
        if host and not self.config.is_allowed_domain(host):
            logger.warning("Listing host '%s' not allowed. Skipping item.", host)
            return None
        return parsed
