"""Alembic environment. The connection comes from Settings (.env / environment variables)."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from real_estate_price_tracking_systems.infrastructure.config import load_settings

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The schema is written as SQL in versions/*.py; there are no SQLAlchemy models to diff against.
target_metadata = None


def get_url() -> str:
    # Settings builds a libpq URL; select the psycopg 3 driver instead of SQLAlchemy's default
    # psycopg2, which is not installed.
    return load_settings().postgres_dsn.replace("postgresql://", "postgresql+psycopg://", 1)


def run_migrations_offline() -> None:
    """``alembic upgrade head --sql``: print the SQL instead of connecting (renders init.sql)."""
    # paramstyle="named" stops the psycopg dialect doubling every "%" in the output, which would
    # break format('%I') inside plpgsql bodies.
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section) or {}
    section["sqlalchemy.url"] = get_url()
    engine = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
