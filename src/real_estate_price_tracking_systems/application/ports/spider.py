from collections.abc import AsyncIterator
from typing import Any, Protocol

from real_estate_price_tracking_systems.domain.entities import ParsedListingItem, RunMode


class Spider(Protocol):
    """A site spider.

    After ``crawl`` finishes, the three attributes describe how it ended; the crawl use case's
    health gate relies on them to decide whether a full sweep is trustworthy enough to expire
    the listings it did not see.
    """

    pages_crawled: int
    aborted_reason: str | None  # set when the crawl stopped on an error or a block
    exhausted: bool  # True only when the end of the listings was really reached

    def crawl(
        self, run_mode: RunMode = RunMode.INCREMENTAL
    ) -> AsyncIterator[tuple[ParsedListingItem, dict[str, Any]]]:
        """Yield ``(parsed item, raw payload)`` pairs. Implementations are async generators."""
        ...
