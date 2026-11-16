"""PostgreSQL implementation of :class:`CrawlRunRepository`."""

from typing import Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from real_estate_price_tracking_systems.application.ports import CrawlRunRepository
from real_estate_price_tracking_systems.domain.entities import CrawlRunStatus, RunMode

_CREATE = """
    INSERT INTO crawl_runs (crawl_run_id, site_id, run_mode, status, started_at)
    VALUES (%s, %s, %s, 'running', NOW())
    RETURNING crawl_run_id, site_id, run_mode, status, started_at
"""
_UPDATE_METRICS = """
    UPDATE crawl_runs
    SET items_scraped = items_scraped + %s, pages_crawled = GREATEST(pages_crawled, %s)
    WHERE crawl_run_id = %s
"""
_COMPLETE = """
    UPDATE crawl_runs SET status = %s, finished_at = NOW(), error_message = %s
    WHERE crawl_run_id = %s
"""
_ABORT_STALE = """
    UPDATE crawl_runs
    SET status = 'failed', finished_at = NOW(), error_message = %s
    WHERE site_id = %s AND status = 'running'
      AND started_at < NOW() - make_interval(mins => %s)
"""
_FAIL_INTERRUPTED = """
    UPDATE crawl_runs
    SET status = 'failed', finished_at = NOW(), error_message = %s
    WHERE status = 'running' AND started_at < NOW() - make_interval(mins => %s)
"""


class PostgresCrawlRunRepository(CrawlRunRepository):
    """Crawl run sessions and their counters in ``crawl_runs``."""

    def __init__(self, pool: AsyncConnectionPool) -> None:
        self._pool = pool

    async def create_run(
        self, crawl_run_id: str, site_id: str, run_mode: RunMode = RunMode.INCREMENTAL
    ) -> dict[str, Any]:
        """Insert a ``running`` row.

        A second ``running`` run for the same feed violates the partial unique index and raises
        ``psycopg.errors.UniqueViolation``: that is the guard against two schedulers.
        """
        async with self._pool.connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(_CREATE, (crawl_run_id, site_id, RunMode(run_mode).value))
            row = await cur.fetchone()
        if row is None:  # INSERT ... RETURNING always yields the row
            raise RuntimeError("INSERT ... RETURNING returned no row")
        return row

    async def update_metrics(
        self, crawl_run_id: str, *, items_scraped: int = 0, pages_crawled: int = 0
    ) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(_UPDATE_METRICS, (items_scraped, pages_crawled, crawl_run_id))

    async def complete_run(
        self,
        crawl_run_id: str,
        status: CrawlRunStatus = CrawlRunStatus.COMPLETED,
        error_message: str | None = None,
    ) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                _COMPLETE, (CrawlRunStatus(status).value, error_message, crawl_run_id)
            )

    async def abort_stale_runs(self, site_id: str, max_age_minutes: int = 60) -> int:
        message = f"Aborted: still running after {max_age_minutes} minutes"
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(_ABORT_STALE, (message, site_id, max_age_minutes))
            return cur.rowcount

    async def fail_interrupted_runs(self, max_age_minutes: int = 60) -> int:
        message = "Interrupted: still running when the scheduler restarted"
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(_FAIL_INTERRUPTED, (message, max_age_minutes))
            return cur.rowcount
