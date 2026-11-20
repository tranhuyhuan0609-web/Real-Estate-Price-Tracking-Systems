"""Per-crawl pool of HTTP clients: one keep-alive client per proxy, reused for every request."""

from __future__ import annotations

import time
from types import TracebackType
from typing import Any

import httpx

from real_estate_price_tracking_systems.domain.entities import ProxySettings


class HttpClientPool:
    """Owns the ``httpx.AsyncClient`` objects of one crawl session.

    * No proxy configured: a single direct client.
    * Proxy enabled, rotation disabled: a single client through the first proxy.
    * Rotation enabled: one client per proxy; every request (including retries) moves to the
      next proxy, so a blocked proxy is not retried against itself.
    * Consecutive failures put a proxy on cooldown (``ProxySettings.max_failures`` and
      ``cooldown_seconds``); rotation skips it until the cooldown ends. A success clears the count.

    Clients are created on ``__aenter__`` and kept for the whole crawl, so TCP/TLS connections
    are pooled instead of re-established per request.
    """

    def __init__(self, proxy_settings: ProxySettings | None, **client_kwargs: Any) -> None:
        proxies: list[str | None] = [None]
        rotate = False
        max_failures = 3
        cooldown_seconds = 60
        if proxy_settings is not None and proxy_settings.enabled and proxy_settings.proxies:
            rotate = proxy_settings.rotation_enabled
            proxies = list(proxy_settings.proxies) if rotate else [proxy_settings.proxies[0]]
            max_failures = proxy_settings.max_failures
            cooldown_seconds = proxy_settings.cooldown_seconds

        self._proxies = proxies
        self._rotate = rotate
        self._max_failures = max_failures
        self._cooldown_seconds = cooldown_seconds
        self._client_kwargs = client_kwargs
        self._clients: list[httpx.AsyncClient] = []
        self._index = 0
        self._failures: dict[httpx.AsyncClient, int] = {}
        self._cooldown_until: dict[httpx.AsyncClient, float] = {}

    async def __aenter__(self) -> HttpClientPool:
        for proxy in self._proxies:
            kwargs = dict(self._client_kwargs)
            if proxy is not None:
                kwargs["proxy"] = proxy
            self._clients.append(httpx.AsyncClient(**kwargs))
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        clients, self._clients = self._clients, []
        for client in clients:
            await client.aclose()

    def record_success(self, client: httpx.AsyncClient) -> None:
        """A good response clears the failure count and any cooldown."""
        self._failures[client] = 0
        self._cooldown_until.pop(client, None)

    def record_failure(self, client: httpx.AsyncClient) -> None:
        """Count a consecutive failure; at ``max_failures`` the proxy cools down."""
        failures = self._failures.get(client, 0) + 1
        self._failures[client] = failures
        if failures >= self._max_failures:
            self._cooldown_until[client] = time.monotonic() + self._cooldown_seconds
            self._failures[client] = 0

    def next(self) -> httpx.AsyncClient:
        """Client for the next request: round-robin over the proxies not cooling down."""
        if not self._clients:
            raise RuntimeError("HttpClientPool used outside of 'async with'.")
        if not self._rotate or len(self._clients) == 1:
            return self._clients[0]

        now = time.monotonic()
        total = len(self._clients)
        for offset in range(total):
            index = (self._index + offset) % total
            candidate = self._clients[index]
            if self._cooldown_until.get(candidate, 0.0) <= now:
                self._index = (index + 1) % total
                return candidate

        # Every proxy is cooling down: keep crawling round-robin rather than stalling.
        client = self._clients[self._index % total]
        self._index = (self._index + 1) % total
        return client
