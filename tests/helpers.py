"""Shared test doubles (import as ``from tests.helpers import ...``)."""

from unittest.mock import AsyncMock, MagicMock


def make_mock_pool(cursor: AsyncMock) -> MagicMock:
    """A psycopg ``AsyncConnectionPool`` double whose connections yield ``cursor``.

    ``pool.connection()`` gives a connection; ``connection.transaction()`` and
    ``connection.cursor()`` are async context managers and ``connection.execute`` is an
    ``AsyncMock`` (reach it with ``connection_of(pool)``).
    """
    conn = AsyncMock()
    conn.transaction = MagicMock()
    conn.transaction.return_value.__aenter__ = AsyncMock(return_value=conn)
    conn.transaction.return_value.__aexit__ = AsyncMock(return_value=None)
    conn.cursor = MagicMock()
    conn.cursor.return_value.__aenter__ = AsyncMock(return_value=cursor)
    conn.cursor.return_value.__aexit__ = AsyncMock(return_value=None)

    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


def connection_of(pool: MagicMock) -> AsyncMock:
    """The connection a ``make_mock_pool`` pool hands out."""
    conn: AsyncMock = pool.connection.return_value.__aenter__.return_value
    return conn
