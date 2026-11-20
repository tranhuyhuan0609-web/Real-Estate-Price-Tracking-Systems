"""HttpClientPool: one client per proxy, rotation, and cooldown of failing proxies."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from real_estate_price_tracking_systems.domain.entities import ProxySettings
from real_estate_price_tracking_systems.infrastructure.crawler import http_clients
from real_estate_price_tracking_systems.infrastructure.crawler.http_clients import HttpClientPool

P = ["http://p1:8080", "http://p2:8080", "http://p3:8080"]


@pytest.fixture
def fake_httpx(monkeypatch: pytest.MonkeyPatch) -> list[MagicMock]:
    made: list[MagicMock] = []

    def factory(**kwargs: Any) -> MagicMock:
        client = MagicMock(proxy=kwargs.get("proxy"), kwargs=kwargs)
        client.aclose = AsyncMock()
        made.append(client)
        return client

    monkeypatch.setattr("httpx.AsyncClient", factory)
    return made


def rotating(**overrides: Any) -> ProxySettings:
    return ProxySettings(enabled=True, rotation_enabled=True, proxies=P, **overrides)


async def test_rotation_reuses_one_client_per_proxy(fake_httpx: list[MagicMock]) -> None:
    async with HttpClientPool(rotating(), follow_redirects=True) as pool:
        used = [pool.next().proxy for _ in range(7)]
    assert used == [P[0], P[1], P[2], P[0], P[1], P[2], P[0]]
    assert len(fake_httpx) == 3  # not one client per request
    assert all(client.aclose.await_count == 1 for client in fake_httpx)


async def test_client_kwargs_reach_every_client(fake_httpx: list[MagicMock]) -> None:
    async with HttpClientPool(rotating(), follow_redirects=True, headers={"X": "1"}):
        pass
    assert len(fake_httpx) == 3
    for client, proxy in zip(fake_httpx, P, strict=True):
        assert client.kwargs == {"follow_redirects": True, "headers": {"X": "1"}, "proxy": proxy}


async def test_proxy_without_rotation_sticks_to_first(fake_httpx: list[MagicMock]) -> None:
    async with HttpClientPool(ProxySettings(enabled=True, proxies=P)) as pool:
        assert {pool.next().proxy for _ in range(3)} == {P[0]}
    assert len(fake_httpx) == 1


async def test_disabled_proxies_are_ignored(fake_httpx: list[MagicMock]) -> None:
    async with HttpClientPool(ProxySettings(enabled=False)) as pool:
        assert pool.next().proxy is None


async def test_no_proxy_is_a_single_direct_client(fake_httpx: list[MagicMock]) -> None:
    async with HttpClientPool(None) as pool:
        assert pool.next() is pool.next()
    assert fake_httpx[0].proxy is None


def test_pool_must_be_entered() -> None:
    with pytest.raises(RuntimeError, match="outside of 'async with'"):
        HttpClientPool(None).next()


async def test_clients_are_closed_even_when_the_body_raises(fake_httpx: list[MagicMock]) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        async with HttpClientPool(rotating()):
            raise RuntimeError("boom")
    assert all(client.aclose.await_count == 1 for client in fake_httpx)


# --- cooldown -------------------------------------------------------------------------------


async def test_failing_proxy_is_skipped_after_max_failures(fake_httpx: list[MagicMock]) -> None:
    async with HttpClientPool(rotating(max_failures=2, cooldown_seconds=60)) as pool:
        first = pool.next()
        assert first.proxy == P[0]
        pool.record_failure(first)
        pool.record_failure(first)

        used = [pool.next().proxy for _ in range(4)]
        assert used == [P[1], P[2], P[1], P[2]]


async def test_a_success_resets_the_failure_count(fake_httpx: list[MagicMock]) -> None:
    async with HttpClientPool(rotating(max_failures=2, cooldown_seconds=60)) as pool:
        first = pool.next()
        pool.record_failure(first)
        pool.record_success(first)
        pool.record_failure(first)  # one failure since the success: not cooled down

        assert [pool.next().proxy for _ in range(3)] == [P[1], P[2], P[0]]


async def test_cooldown_ends(fake_httpx: list[MagicMock], monkeypatch: pytest.MonkeyPatch) -> None:
    now = [1000.0]
    monkeypatch.setattr(http_clients.time, "monotonic", lambda: now[0])
    async with HttpClientPool(rotating(max_failures=1, cooldown_seconds=30)) as pool:
        first = pool.next()
        pool.record_failure(first)
        assert P[0] not in [pool.next().proxy for _ in range(4)]

        now[0] += 31
        assert P[0] in [pool.next().proxy for _ in range(3)]


async def test_success_ends_a_cooldown_early(fake_httpx: list[MagicMock]) -> None:
    async with HttpClientPool(rotating(max_failures=1, cooldown_seconds=60)) as pool:
        first = pool.next()
        pool.record_failure(first)
        pool.record_success(first)
        assert P[0] in [pool.next().proxy for _ in range(3)]


async def test_when_every_proxy_is_cooling_down_rotation_continues(
    fake_httpx: list[MagicMock],
) -> None:
    async with HttpClientPool(rotating(max_failures=1, cooldown_seconds=60)) as pool:
        for _ in range(3):
            pool.record_failure(pool.next())
        assert [pool.next().proxy for _ in range(4)] == [P[0], P[1], P[2], P[0]]
