"""Per-crawl pool of HTTP clients: one keep-alive client per proxy, reused for every request."""

from __future__ import annotations

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

    Clients are created on ``__aenter__`` and kept for the whole crawl, so TCP/TLS connections
    are pooled instead of re-established per request.
    """

    def __init__(self, proxy_settings: ProxySettings | None, **client_kwargs: Any) -> None:
        proxies: list[str | None] = [None]
        rotate = False
        if proxy_settings is not None and proxy_settings.enabled and proxy_settings.proxies:
            rotate = proxy_settings.rotation_enabled
            proxies = list(proxy_settings.proxies) if rotate else [proxy_settings.proxies[0]]

        self._proxies = proxies
        self._rotate = rotate
        self._client_kwargs = client_kwargs
        self._clients: list[httpx.AsyncClient] = []
        self._index = 0

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

    def next(self) -> httpx.AsyncClient:
        """Client for the next request: round-robin over the proxies when rotating."""
        if not self._clients:
            raise RuntimeError("HttpClientPool used outside of 'async with'.")
        if not self._rotate or len(self._clients) == 1:
            return self._clients[0]
        client = self._clients[self._index % len(self._clients)]
        self._index = (self._index + 1) % len(self._clients)
        return client
