# Naming conventions

Every name below must be identical everywhere it appears. Change a value here first, then in
the files listed.

| What | Value | Must match in |
|---|---|---|
| Python package | `real_estate_price_tracking_systems` | `src/<pkg>/`, `pyproject.toml` (isort, mypy, coverage), imports |
| Distribution name | `real-estate-price-tracking-systems` | `pyproject.toml`, `__init__.py` (`version(...)`) |
| Docker compose project | `real-estate-price-tracking-systems` | `docker/docker-compose.yml` (`name:`). Volume names derive from it: renaming loses data |
| Postgres database / user | `Property_data` / `huyhuan` | `.env`, `.env.example` |
| Mongo database / user | `Property_data` / `huyhuan` | `.env`, `.env.example` |
| Compose service hostnames | `postgres`, `mongo`, `kafka` | compose env (`POSTGRES_HOST`...), backup scripts, Prometheus scrape config |
| Kafka topics | `Property_data.raw_events`, `Property_data.dlq_events` | `.env`, `kafka-setup` job |
| Consumer groups | `bds_bronze_mongo_groups`, `bds_silver_gold_pg_groups`, `bds_dlq_writer_groups` | `.env` (bronze and silver/gold must differ) |
| Metric prefix | `realestate_` | metrics module, alert rules |
| Host ports | `17100` Kafka, `17101` Kafka UI, `17102` MongoDB, `17103` PostgreSQL, `17104` Prometheus, `17105` Alertmanager | `.env` (`*_HOST_PORT`), compose, README |

Ports 16100-16105 belong to the previous version of this project, so both stacks can run side
by side on one machine. Passwords are never written here or in `.env.example`: only in `.env`.

Official images fix the *variable names* (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`,
`MONGO_INITDB_ROOT_USERNAME`, `MONGO_INITDB_ROOT_PASSWORD`); only their values are ours.

## Branches and commits

- Branch: `type/short-description`, e.g. `feat/html-spider`, `fix/xpath-quoting`
- Commit: `type(scope): imperative subject` ([Conventional Commits](https://www.conventionalcommits.org/));
  the body explains *why*
- Types: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`, `chore`
- Merge: pull request + merge commit, branch deleted after merge
