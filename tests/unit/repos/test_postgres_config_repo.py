"""PostgresConfigRepository against a fake pool: the SQL it sends and the errors it raises."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from real_estate_price_tracking_systems.domain.entities import CrawlerConfig
from real_estate_price_tracking_systems.domain.exceptions import (
    ConfigAlreadyExistsError,
    ConfigNotFoundError,
)
from real_estate_price_tracking_systems.infrastructure.persistence.postgres.config_repo import (
    PostgresConfigRepository,
)
from tests.helpers import connection_of, make_mock_pool


def build(**cursor_attrs: Any) -> tuple[PostgresConfigRepository, AsyncMock, MagicMock]:
    cursor = AsyncMock()
    for name, value in cursor_attrs.items():
        # fetchone/fetchall are awaited; rowcount is a plain attribute
        setattr(cursor, name, AsyncMock(return_value=value) if name.startswith("fetch") else value)
    pool = make_mock_pool(cursor)
    return PostgresConfigRepository(pool), cursor, pool


def sql_of(cursor: AsyncMock) -> str:
    return str(cursor.execute.call_args[0][0])


async def test_get_config_returns_the_model(
    seed_row: dict[str, Any], config: CrawlerConfig
) -> None:
    repo, cursor, _ = build(fetchone=seed_row)
    assert await repo.get_config("meeyland") == config
    assert cursor.execute.call_args[0][1] == ("meeyland",)


async def test_get_config_not_found() -> None:
    repo, _, _ = build(fetchone=None)
    with pytest.raises(ConfigNotFoundError, match="meeyland"):
        await repo.get_config("meeyland")


async def test_get_enabled_configs_filters_in_sql(
    seed_row: dict[str, Any], config: CrawlerConfig
) -> None:
    repo, cursor, _ = build(fetchall=[seed_row])
    assert await repo.get_enabled_configs() == [config]
    assert "WHERE enabled" in sql_of(cursor)


async def test_create_config_inserts_columns_and_json(config: CrawlerConfig) -> None:
    repo, cursor, _ = build(rowcount=1)
    await repo.create_config(config)
    assert "ON CONFLICT (site_id) DO NOTHING" in sql_of(cursor)
    values = cursor.execute.call_args[0][1]
    assert values[0] == "meeyland"
    assert len(values) == 7  # six columns + config_json


async def test_create_config_duplicate(config: CrawlerConfig) -> None:
    repo, _, _ = build(rowcount=0)
    with pytest.raises(ConfigAlreadyExistsError, match="meeyland"):
        await repo.create_config(config)


async def test_update_config_updates_by_site_id(config: CrawlerConfig) -> None:
    repo, cursor, _ = build(rowcount=1)
    await repo.update_config("meeyland", config)
    assert cursor.execute.call_args[0][1][-1] == "meeyland"
    assert "updated_at = NOW()" in sql_of(cursor)


async def test_update_config_rejects_a_different_site(config: CrawlerConfig) -> None:
    repo, cursor, _ = build(rowcount=1)
    with pytest.raises(ValueError, match="does not match"):
        await repo.update_config("mogi", config)
    cursor.execute.assert_not_called()


async def test_update_config_not_found(config: CrawlerConfig) -> None:
    repo, _, _ = build(rowcount=0)
    with pytest.raises(ConfigNotFoundError):
        await repo.update_config("meeyland", config)


async def test_delete_config() -> None:
    repo, cursor, _ = build(rowcount=1)
    await repo.delete_config("meeyland")
    assert sql_of(cursor).startswith("DELETE FROM crawler_configs")


async def test_delete_config_not_found() -> None:
    repo, _, _ = build(rowcount=0)
    with pytest.raises(ConfigNotFoundError):
        await repo.delete_config("meeyland")


async def test_update_last_run() -> None:
    repo, cursor, _ = build(rowcount=1)
    await repo.update_last_run("meeyland")
    assert "last_run_at = NOW()" in sql_of(cursor)
    assert cursor.execute.call_args[0][1] == ("meeyland",)


async def test_update_last_run_not_found() -> None:
    repo, _, _ = build(rowcount=0)
    with pytest.raises(ConfigNotFoundError, match="meeyland"):
        await repo.update_last_run("meeyland")


async def test_every_query_sets_a_local_statement_timeout() -> None:
    cursor = AsyncMock(rowcount=1)
    pool = make_mock_pool(cursor)
    repo = PostgresConfigRepository(pool, query_timeout=2.5)
    await repo.update_last_run("meeyland")
    connection_of(pool).execute.assert_awaited_once_with(
        "SELECT set_config('statement_timeout', %s, true)", ("2500",)
    )


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), True])
def test_invalid_query_timeout(timeout: float) -> None:
    with pytest.raises(ValueError, match="timeout"):
        PostgresConfigRepository(make_mock_pool(AsyncMock()), query_timeout=timeout)
