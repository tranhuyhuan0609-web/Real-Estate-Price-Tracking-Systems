"""GenericApiSpider driven through httpx's MockTransport: the real request/retry/parse path, no network."""

import copy
import json
from collections.abc import Callable
from typing import Any

import httpx

from real_estate_price_tracking_systems.domain.entities import CrawlerConfig, RunMode
from real_estate_price_tracking_systems.infrastructure.crawler.spiders.generic_api_spider import (
    GenericApiSpider,
)
from tests.unit.spiders.conftest import Handler


def base_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "site_id": "demo",
        "name": "Demo",
        "interval_seconds": 300,
        "rate_limit": {"download_delay_sec": 0.001, "retry_times": 2, "timeout_sec": 5},
        "request": {"url": "https://api.example.com/search", "method": "POST", "body_template": {}},
        "pagination": {
            "param_location": "body",
            "page_size": 2,
            "max_pages_incremental": 5,
            "max_pages_full_sweep": 50,
            "stop_when_empty_path": "data",
        },
        "response_mapping": {
            "items_path": "data",
            "fields": {
                "external_code": "code",
                "url": "link",
                "title": "title",
                "price_vnd": "price",
                "area_m2": "area",
            },
        },
    }
    data.update(overrides)
    return data


def make_config(**overrides: Any) -> CrawlerConfig:
    return CrawlerConfig.model_validate(copy.deepcopy(base_data(**overrides)))


def item(code: int, **extra: Any) -> dict[str, Any]:
    return {
        "code": code,
        "title": f"Bán đất {code}",
        "link": f"https://api.example.com/d/{code}",
        "price": "2 tỷ",
        "area": 100,
        **extra,
    }


def page(*items: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"data": list(items)})


def by_page(pages: list[httpx.Response]) -> Handler:
    """Answer request n with pages[n]; the last page repeats."""
    state = {"n": 0}

    def handler(request: httpx.Request, proxy: str | None) -> httpx.Response:
        response = pages[min(state["n"], len(pages) - 1)]
        state["n"] += 1
        return response

    return handler


async def crawl(
    spider: GenericApiSpider, mode: RunMode = RunMode.INCREMENTAL
) -> list[tuple[Any, dict[str, Any]]]:
    return [pair async for pair in spider.crawl(mode)]


def spider_for(config: CrawlerConfig) -> GenericApiSpider:
    return GenericApiSpider(config, retry_backoff_sec=0.001)


# --- the happy path and how it ends ----------------------------------------------------------


async def test_crawl_yields_every_item_until_the_end(serve: Callable[[Handler], None]) -> None:
    serve(by_page([page(item(1), item(2)), page(item(3)), page()]))
    spider = spider_for(make_config())

    results = await crawl(spider)

    assert [parsed.external_code for parsed, _ in results] == [1, 2, 3]
    assert results[0][0].listing_key == "demo_1"
    assert results[0][1]["title"] == "Bán đất 1"  # the raw payload comes along
    assert results[0][0].current_price_vnd == 2_000_000_000
    assert spider.exhausted is True and spider.aborted_reason is None
    assert spider.pages_crawled == 3


async def test_reaching_the_page_budget_is_neither_exhausted_nor_aborted(
    serve: Callable[[Handler], None],
) -> None:
    serve(by_page([page(item(1), item(2))]))  # an endless supply of pages
    config = make_config(
        pagination={
            **base_data()["pagination"],
            "max_pages_incremental": 2,
            "max_pages_full_sweep": 4,
        }
    )
    spider = spider_for(config)

    assert len(await crawl(spider)) == 4  # 2 pages of the same 2 items
    assert (spider.pages_crawled, spider.exhausted, spider.aborted_reason) == (2, False, None)

    await crawl(spider, RunMode.FULL_SWEEP)
    assert spider.pages_crawled == 4  # the full sweep has the bigger budget


async def test_an_empty_first_page_is_an_abort_not_the_end(
    serve: Callable[[Handler], None],
) -> None:
    serve(by_page([page()]))
    spider = spider_for(make_config())

    assert await crawl(spider) == []
    assert spider.exhausted is False
    assert spider.aborted_reason is not None and "first page" in spider.aborted_reason


async def test_flags_are_reset_by_every_crawl(serve: Callable[[Handler], None]) -> None:
    serve(by_page([page(item(1)), page()]))
    spider = spider_for(make_config())
    await crawl(spider)
    assert spider.exhausted is True

    serve(by_page([page()]))  # now the very first page is empty
    await crawl(spider)
    assert spider.exhausted is False and spider.aborted_reason is not None


async def test_missing_items_path_aborts(serve: Callable[[Handler], None]) -> None:
    """The stop path has a list but the mapping's items path does not."""
    config = make_config(
        response_mapping={**base_data()["response_mapping"], "items_path": "other.list"}
    )
    serve(by_page([page(item(1))]))
    spider = spider_for(config)

    assert await crawl(spider) == []
    assert spider.aborted_reason is not None and "other.list" in spider.aborted_reason
    assert spider.exhausted is False


# --- failures and retries --------------------------------------------------------------------


async def test_retryable_status_is_retried_then_succeeds(serve: Callable[[Handler], None]) -> None:
    serve(by_page([httpx.Response(503), httpx.Response(429), page(item(1)), page()]))
    spider = spider_for(make_config())

    results = await crawl(spider)

    assert [parsed.external_code for parsed, _ in results] == [1]
    assert spider.aborted_reason is None and spider.exhausted is True


async def test_running_out_of_retries_aborts(
    serve: Callable[[Handler], None], requests_seen: list[Any]
) -> None:
    serve(by_page([httpx.Response(503)]))
    spider = spider_for(make_config())  # retry_times=2 -> 3 attempts

    assert await crawl(spider) == []
    assert len(requests_seen) == 3
    assert spider.aborted_reason is not None and "page 1" in spider.aborted_reason
    assert spider.exhausted is False and spider.pages_crawled == 0


async def test_a_client_error_is_not_retried(
    serve: Callable[[Handler], None], requests_seen: list[Any]
) -> None:
    serve(by_page([httpx.Response(403)]))
    spider = spider_for(make_config())

    assert await crawl(spider) == []
    assert len(requests_seen) == 1
    assert spider.aborted_reason is not None


async def test_network_errors_are_retried_then_abort(
    serve: Callable[[Handler], None], requests_seen: list[Any]
) -> None:
    def handler(request: httpx.Request, proxy: str | None) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    serve(handler)
    spider = spider_for(make_config())

    assert await crawl(spider) == []  # no exception escapes the generator
    assert len(requests_seen) == 3
    assert spider.aborted_reason is not None and "Network error" in spider.aborted_reason


async def test_a_network_error_followed_by_success_recovers(
    serve: Callable[[Handler], None],
) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request, proxy: str | None) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("slow", request=request)
        return page(item(1)) if calls["n"] == 2 else page()

    serve(handler)
    spider = spider_for(make_config())

    assert len(await crawl(spider)) == 1
    assert spider.aborted_reason is None and spider.exhausted is True


async def test_invalid_json_aborts(serve: Callable[[Handler], None]) -> None:
    serve(by_page([httpx.Response(200, content=b"<html>blocked</html>")]))
    spider = spider_for(make_config())

    assert await crawl(spider) == []
    assert spider.aborted_reason is not None and "Invalid JSON" in spider.aborted_reason


# --- what is sent ----------------------------------------------------------------------------


async def test_post_body_carries_the_page_and_limit(
    serve: Callable[[Handler], None], requests_seen: list[Any]
) -> None:
    config = make_config(
        request={
            "url": "https://api.example.com/search",
            "method": "POST",
            "body_template": {"sort": 2},
        }
    )
    serve(by_page([page(item(1)), page()]))
    await crawl(spider_for(config))

    bodies = [json.loads(request.content) for request, _ in requests_seen]
    assert bodies == [
        {"sort": 2, "page": 1, "limit": 2},
        {"sort": 2, "page": 2, "limit": 2},
    ]


async def test_query_pagination_for_get(
    serve: Callable[[Handler], None], requests_seen: list[Any]
) -> None:
    config = make_config(
        request={"url": "https://api.example.com/search", "query_params": {"city": "hn"}},
        pagination={**base_data()["pagination"], "param_location": "query"},
    )
    serve(by_page([page(item(1)), page()]))
    await crawl(spider_for(config))

    first = requests_seen[0][0]
    assert first.method == "GET"
    assert dict(first.url.params) == {"city": "hn", "page": "1", "limit": "2"}
    assert not first.content  # a GET has no body


async def test_offset_limit_pagination(
    serve: Callable[[Handler], None], requests_seen: list[Any]
) -> None:
    config = make_config(
        request={"url": "https://api.example.com/search"},
        pagination={
            **base_data()["pagination"],
            "strategy": "offset_limit",
            "param_location": "query",
            "page_param": "offset",
            "start_page": 0,
        },
    )
    serve(by_page([page(item(1), item(2)), page(item(3)), page()]))
    await crawl(spider_for(config))

    assert [dict(request.url.params)["offset"] for request, _ in requests_seen] == ["0", "2", "4"]


async def test_default_user_agent_and_configured_headers(
    serve: Callable[[Handler], None], requests_seen: list[Any]
) -> None:
    config = make_config(
        request={
            "url": "https://api.example.com/search",
            "method": "POST",
            "headers": {"X-Api": "k"},
            "body_template": {},
        }
    )
    serve(by_page([page()]))
    await crawl(spider_for(config))

    headers = requests_seen[0][0].headers
    assert headers["x-api"] == "k" and "RealEstateBot" in headers["user-agent"]


# --- items -----------------------------------------------------------------------------------


async def test_an_unparseable_item_is_counted_and_skipped(serve: Callable[[Handler], None]) -> None:
    broken = {"title": "no id at all", "link": "https://api.example.com/x"}
    serve(by_page([page(item(1), broken, item(3)), page()]))
    spider = spider_for(make_config())

    results = await crawl(spider)

    assert [parsed.external_code for parsed, _ in results] == [1, 3]
    assert spider.parse_errors == 1
    assert spider.aborted_reason is None  # one bad item does not abort the crawl


async def test_items_on_a_foreign_host_are_skipped(serve: Callable[[Handler], None]) -> None:
    ad = item(2, link="https://evil.example.org/ad/2")
    serve(by_page([page(item(1), ad), page()]))

    results = await crawl(spider_for(make_config()))

    assert [parsed.external_code for parsed, _ in results] == [1]


async def test_non_object_items_are_ignored(serve: Callable[[Handler], None]) -> None:
    serve(by_page([httpx.Response(200, json={"data": [item(1), "junk", None, 7]}), page()]))

    results = await crawl(spider_for(make_config()))

    assert [parsed.external_code for parsed, _ in results] == [1]


# --- proxies ---------------------------------------------------------------------------------

PROXIES = ["http://p1:8080", "http://p2:8080", "http://p3:8080"]


async def test_every_page_uses_the_next_proxy(
    serve: Callable[[Handler], None], requests_seen: list[Any]
) -> None:
    config = make_config(
        proxy_settings={"enabled": True, "rotation_enabled": True, "proxies": PROXIES}
    )
    serve(by_page([page(item(1)), page(item(2)), page(item(3)), page(item(4)), page()]))

    await crawl(spider_for(config))

    assert [proxy for _, proxy in requests_seen] == [*PROXIES, PROXIES[0], PROXIES[1]]


async def test_a_retry_moves_to_another_proxy(
    serve: Callable[[Handler], None], requests_seen: list[Any]
) -> None:
    config = make_config(
        proxy_settings={"enabled": True, "rotation_enabled": True, "proxies": PROXIES}
    )

    def handler(request: httpx.Request, proxy: str | None) -> httpx.Response:
        if proxy == PROXIES[0]:
            return httpx.Response(429)  # the first proxy is rate limited
        return page(item(1)) if len(requests_seen) < 3 else page()

    serve(handler)
    spider = spider_for(config)

    results = await crawl(spider)

    assert [proxy for _, proxy in requests_seen][:2] == [PROXIES[0], PROXIES[1]]
    assert len(results) == 1 and spider.aborted_reason is None


async def test_failures_cool_the_proxy_down(
    serve: Callable[[Handler], None], requests_seen: list[Any]
) -> None:
    """The spider must report failures to the pool, or a dead proxy is retried on every lap."""
    config = make_config(
        proxy_settings={
            "enabled": True,
            "rotation_enabled": True,
            "proxies": PROXIES,
            "max_failures": 1,
            "cooldown_seconds": 600,
        }
    )
    served = {"pages": 0}

    def handler(request: httpx.Request, proxy: str | None) -> httpx.Response:
        if proxy == PROXIES[0]:
            return httpx.Response(503)  # always down
        served["pages"] += 1
        return page(item(served["pages"])) if served["pages"] <= 3 else page()

    serve(handler)
    await crawl(spider_for(config))

    # p1 fails once and then sits out: p2, p3, p2, p3 ... never p1 again.
    assert [proxy for _, proxy in requests_seen] == [
        PROXIES[0],
        PROXIES[1],
        PROXIES[2],
        PROXIES[1],
        PROXIES[2],
    ]
