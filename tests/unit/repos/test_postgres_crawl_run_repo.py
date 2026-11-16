from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from real_estate_price_tracking_systems.domain.entities import CrawlRunStatus, RunMode
from real_estate_price_tracking_systems.infrastructure.persistence.postgres.crawl_run_repo import (
    PostgresCrawlRunRepository,
)
from tests.helpers import connection_of, make_mock_pool


def build(**cursor_attrs: Any) -> tuple[PostgresCrawlRunRepository, AsyncMock, MagicMock]:
    cursor = AsyncMock()
    for name, value in cursor_attrs.items():
        # fetchone/fetchall are awaited; rowcount is a plain attribute
        setattr(cursor, name, AsyncMock(return_value=value) if name.startswith("fetch") else value)
    pool = make_mock_pool(cursor)
    return PostgresCrawlRunRepository(pool), cursor, pool


async def test_create_run_returns_the_inserted_row() -> None:
    row = {"crawl_run_id": "r1", "site_id": "mogi", "run_mode": "full_sweep", "status": "running"}
    repo, cursor, _ = build(fetchone=row)
    assert await repo.create_run("r1", "mogi", RunMode.FULL_SWEEP) == row
    assert cursor.execute.call_args[0][1] == ("r1", "mogi", "full_sweep")


async def test_create_run_defaults_to_incremental() -> None:
    repo, cursor, _ = build(fetchone={})
    await repo.create_run("r1", "mogi")
    assert cursor.execute.call_args[0][1][2] == "incremental"


async def test_create_run_rejects_an_unknown_mode() -> None:
    repo, cursor, _ = build(fetchone={})
    with pytest.raises(ValueError, match="weekly"):
        await repo.create_run("r1", "mogi", "weekly")  # type: ignore[arg-type]
    cursor.execute.assert_not_called()


async def test_update_metrics_adds_items_and_keeps_page_high_water_mark() -> None:
    repo, _, pool = build()
    await repo.update_metrics("r1", items_scraped=20, pages_crawled=3)
    sql, params = connection_of(pool).execute.call_args[0]
    assert "items_scraped + %s" in sql and "GREATEST(pages_crawled, %s)" in sql
    assert params == (20, 3, "r1")


async def test_complete_run_stores_status_and_error() -> None:
    repo, _, pool = build()
    await repo.complete_run("r1", CrawlRunStatus.FAILED, "boom")
    assert connection_of(pool).execute.call_args[0][1] == ("failed", "boom", "r1")


async def test_complete_run_defaults_to_completed() -> None:
    repo, _, pool = build()
    await repo.complete_run("r1")
    assert connection_of(pool).execute.call_args[0][1] == ("completed", None, "r1")


async def test_abort_stale_runs_returns_the_count() -> None:
    repo, cursor, _ = build(rowcount=2)
    assert await repo.abort_stale_runs("mogi", max_age_minutes=30) == 2
    message, site_id, minutes = cursor.execute.call_args[0][1]
    assert (site_id, minutes) == ("mogi", 30)
    assert "30 minutes" in message


async def test_fail_interrupted_runs_returns_the_count() -> None:
    repo, cursor, _ = build(rowcount=3)
    assert await repo.fail_interrupted_runs(max_age_minutes=10) == 3
    assert cursor.execute.call_args[0][1][1] == 10
