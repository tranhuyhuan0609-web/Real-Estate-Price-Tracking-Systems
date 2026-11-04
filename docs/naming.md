# Naming conventions

Every name below must be identical everywhere it appears. Change a value here first, then in
the files listed.

| What | Value | Must match in |
|---|---|---|
| Python package | `real_estate_price_tracking_systems` | `src/<pkg>/`, `pyproject.toml` (isort, mypy, coverage), imports |
| Distribution name | `real-estate-price-tracking-systems` | `pyproject.toml`, `__init__.py` (`version(...)`) |
| Docker compose project | `real-estate-price-tracking-systems` | `docker/docker-compose.yml` (`name:`). Volume names derive from it: renaming loses data |
| Postgres database / user | `realestate_db` / `realestate_app` | `.env`, `.env.example` |
| Mongo database / user | `realestate_raw` / `realestate_app` | `.env`, `.env.example` |
| Compose service hostnames | `postgres`, `mongo`, `kafka` | compose env (`POSTGRES_HOST`...), backup scripts, Prometheus scrape config |
| Kafka topics | `realestate.raw_events`, `realestate.dlq_events` | `.env`, `kafka-setup` job |
| Consumer groups | `realestate-bronze`, `realestate-silver-gold`, `realestate-dlq` | `.env` (bronze and silver/gold must differ) |
| Metric prefix | `realestate_` | metrics module, alert rules |
| Host ports | `16100`-`16105` | `.env`, compose, README |

Official images fix the *variable names* (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`,
`MONGO_INITDB_ROOT_USERNAME`, `MONGO_INITDB_ROOT_PASSWORD`); only their values are ours.

## Branches and commits

- Branch: `type/short-description`, e.g. `feat/html-spider`, `fix/xpath-quoting`
- Commit: `type(scope): imperative subject` ([Conventional Commits](https://www.conventionalcommits.org/));
  the body explains *why*
- Types: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci`, `chore`
- Merge: pull request + merge commit, branch deleted after merge
