# Real Estate Price Tracker

[![CI](https://github.com/tranhuyhuan0609-web/Real-Estate-Price-Tracking-Systems/actions/workflows/ci.yml/badge.svg)](https://github.com/tranhuyhuan0609-web/Real-Estate-Price-Tracking-Systems/actions/workflows/ci.yml)
![Python 3.13](https://img.shields.io/badge/python-3.13-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

Event-driven pipeline that crawls Vietnamese real estate listing sites, tracks price changes over
time and computes ward-level price statistics.

```
YAML site configs -> Scheduler -> Spiders -> Kafka -> Bronze (MongoDB, raw payloads)
                                                  \-> Silver (PostgreSQL/PostGIS, clean listings)
                                                       -> Gold (price history, materialized views)
```

- **Hexagonal architecture:** `domain` <- `application` <- `infrastructure` <- `entrypoints`
- **Medallion layers:** raw Bronze, cleaned Silver, analytical Gold
- **At-least-once delivery** with a dead letter queue and replay
- **Declarative sites:** adding a listing site means adding one YAML file

## Status

Built in public, one pull request per milestone. See the
[pull requests](https://github.com/tranhuyhuan0609-web/Real-Estate-Price-Tracking-Systems/pulls?q=is%3Apr)
for the reasoning behind each step.

| Milestone | Scope | Status |
|---|---|---|
| Day 1 | Project skeleton, tooling, CI | done |
| Day 2 | Local Kafka, PostGIS and MongoDB with Docker Compose | done |
| v0.1.0 | Settings, domain model, site configs, database schema | planned |
| v0.2.0 | Parsers, spiders, Kafka, Bronze layer | planned |
| v0.3.0 | Silver/Gold ingestion, scheduler, end-to-end pipeline | planned |
| v1.0.0 | Monitoring, Telegram alerts, backups, docs | planned |

## Development

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) (it installs Python 3.13 from `.python-version`).

```bash
make install    # uv sync --frozen
make check      # ruff + mypy (strict) + pytest - the same checks CI runs
make format     # apply ruff fixes and formatting
```

Without `make` (e.g. Windows): `uv sync --frozen`, `uv run ruff check src tests`, `uv run mypy`, `uv run pytest`.

## Local infrastructure

Requires Docker with Compose v2.

```bash
cp .env.example .env    # then set MONGO_PASSWORD and POSTGRES_PASSWORD
make up                 # Kafka (KRaft), Kafka UI, PostGIS, MongoDB
make ps                 # every service should be "healthy"
make logs S=kafka       # follow one service
make down               # stop; data volumes are kept
```

Without `make`: `docker compose --env-file .env -f docker/docker-compose.yml up -d` (same for `ps`, `logs -f`, `down`).

| Service | From the host | From other containers |
|---|---|---|
| Kafka | `127.0.0.1:17100` | `kafka:19092` |
| Kafka UI | http://localhost:17101 | - |
| MongoDB | `127.0.0.1:17102` | `mongo:27017` |
| PostgreSQL + PostGIS | `127.0.0.1:17103` | `postgres:5432` |

All ports listen on 127.0.0.1 only. Topics `Property_data.raw_events` (4 partitions) and
`Property_data.dlq_events` (2 partitions) are created by the `kafka-setup` job; automatic topic
creation is disabled. This single-broker stack is for development (replication factor 1, no TLS).

## Contributing

Branches follow `type/short-description` (`feat/`, `fix/`, `refactor/`, `test/`, `docs/`, `chore/`),
commits follow [Conventional Commits](https://www.conventionalcommits.org/), and every change lands
through a pull request with a green CI run.

## License

[MIT](LICENSE)
