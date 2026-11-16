import pytest
from psycopg_pool import AsyncConnectionPool

from real_estate_price_tracking_systems.infrastructure.persistence.postgres.connection import (
    create_pg_pool,
)

DSN = "postgresql://u:p@127.0.0.1:1/db"


def test_pool_is_created_closed() -> None:
    pool = create_pg_pool(DSN, min_size=1, max_size=3, timeout=5)
    assert isinstance(pool, AsyncConnectionPool)
    assert pool.closed  # nothing connects until `await pool.open()`
    assert (pool.min_size, pool.max_size, pool.timeout) == (1, 3, 5)


@pytest.mark.parametrize(
    ("min_size", "max_size", "timeout"), [(-1, 5, 1.0), (5, 2, 1.0), (0, 0, 1.0), (1, 2, 0)]
)
def test_invalid_pool_settings(min_size: int, max_size: int, timeout: float) -> None:
    with pytest.raises(ValueError, match="Pool"):
        create_pg_pool(DSN, min_size=min_size, max_size=max_size, timeout=timeout)
