from typing import Any, Protocol

from real_estate_price_tracking_systems.domain.entities import CrawlRunStatus, RunMode


class CrawlRunRepository(Protocol):
    """One row per spider execution. At most one run per feed may be ``running``."""

    async def create_run(
        self, crawl_run_id: str, site_id: str, run_mode: RunMode = RunMode.INCREMENTAL
    ) -> dict[str, Any]: ...

    async def update_metrics(
        self, crawl_run_id: str, *, items_scraped: int = 0, pages_crawled: int = 0
    ) -> None:
        """Add ``items_scraped`` to the counter; ``pages_crawled`` is a high-water mark."""
        ...

    async def complete_run(
        self,
        crawl_run_id: str,
        status: CrawlRunStatus = CrawlRunStatus.COMPLETED,
        error_message: str | None = None,
    ) -> None: ...

    async def abort_stale_runs(self, site_id: str, max_age_minutes: int = 60) -> int:
        """Fail this feed's runs stuck in ``running`` for too long; returns how many."""
        ...

    async def fail_interrupted_runs(self, max_age_minutes: int = 60) -> int:
        """On scheduler start: fail every feed's old ``running`` runs; returns how many."""
        ...
