# ADR 0001: Migrations are the only schema source; price history is partitioned

## Status
Accepted (migration `001_initial`)

## Context
A schema written by hand in two places drifts. The usual pair is `sql/init.sql`, which Postgres
runs on an empty volume, and the Alembic migrations. A database built from `init.sql` has no
`alembic_version`, so the first `alembic upgrade` tries to re-create tables that already exist.

`listing_price_history` is append-only and gets a row for every price change, so it only grows.

## Decision
- `migrations/versions/*.py` is the single schema source. `sql/init.sql` is **generated** by
  `make schema`, which renders `alembic upgrade head --sql`. The generated file also creates and
  stamps `alembic_version`, so a database initialised from it continues at the next revision.
- `tests/contract/test_sql_schema.py` re-renders the file and fails in CI when it is stale.
- Compose mounts `sql/init.sql` into `docker-entrypoint-initdb.d`. Postgres runs it only while the
  data volume is empty; later changes reach existing databases as migrations, never by re-running
  `init.sql`.
- Migrations are raw SQL (`op.execute`), not SQLAlchemy models. The schema uses PostGIS, partial
  indexes, partitioning and plpgsql, none of which models express well, and there is no ORM here
  to keep in sync.
- `listing_price_history` is range-partitioned by month on `recorded_at`; its primary key is
  `(history_id, recorded_at)` because a partitioned table's key must include the partition key.
  `ensure_price_history_partitions(months_ahead)` creates the monthly partitions and is idempotent.
  A DEFAULT partition catches rows outside the created range; when their month is created later,
  the rows are moved out of DEFAULT first, because Postgres refuses to attach a partition that
  overlaps rows in DEFAULT.
- The Gold materialized views each have a UNIQUE index so `REFRESH ... CONCURRENTLY` does not block
  readers.

## Consequences
- A schema change means writing a migration and running `make schema`; CI fails otherwise.
- Old months can be detached or dropped without vacuuming one huge table, and the 7-day drop view
  only scans recent partitions.
- `history_id` alone is not declared unique by the table (the sequence still guarantees it), so the
  steep-drops view keeps its own unique index on it.
- Whoever creates partitions must call `ensure_price_history_partitions` regularly (the scheduler
  does this at startup and daily). Without it, new rows still land in DEFAULT and nothing is lost,
  but they are not pruned by month.
- `--sql` output depends on `paramstyle="named"` in `migrations/env.py`; the default doubles `%`
  and silently breaks `format('%I')` in plpgsql.
