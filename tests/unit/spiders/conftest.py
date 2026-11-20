"""Shared spider-test plumbing: route every httpx client the pool builds through a handler."""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

Handler = Callable[[httpx.Request, str | None], httpx.Response]


@pytest.fixture
def requests_seen() -> list[tuple[httpx.Request, str | None]]:
    return []


@pytest.fixture
def serve(
    monkeypatch: pytest.MonkeyPatch, requests_seen: list[tuple[httpx.Request, str | None]]
) -> Callable[[Handler], None]:
    """Route every AsyncClient the pool builds through ``handler(request, proxy)``."""
    real_client = httpx.AsyncClient

    def install(handler: Handler) -> None:
        def factory(**kwargs: Any) -> httpx.AsyncClient:
            proxy = kwargs.pop("proxy", None)  # a real proxy would bypass the mock transport

            def respond(request: httpx.Request) -> httpx.Response:
                requests_seen.append((request, proxy))
                return handler(request, proxy)

            return real_client(transport=httpx.MockTransport(respond), **kwargs)

        monkeypatch.setattr(httpx, "AsyncClient", factory)

    return install
