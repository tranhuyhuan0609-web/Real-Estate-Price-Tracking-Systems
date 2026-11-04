"""Settings: defaults, escaping, secrets and cross-field rules. Never reads the developer's .env."""

from typing import Any

import pytest
from pydantic import ValidationError

from real_estate_price_tracking_systems.infrastructure.config.base import BASE_DIR
from real_estate_price_tracking_systems.infrastructure.config.settings import (
    Settings,
    load_settings,
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every Settings variable from the process environment."""
    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)


def make(**values: Any) -> Settings:
    """Settings from explicit values only (no .env file)."""
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def test_base_dir_is_the_repository_root() -> None:
    assert (BASE_DIR / "pyproject.toml").is_file()


def test_defaults_match_the_local_stack() -> None:
    s = make()
    assert (s.POSTGRES_HOST, s.POSTGRES_PORT, s.MONGO_PORT) == ("127.0.0.1", 17103, 17102)
    assert s.KAFKA_BOOTSTRAP_SERVERS == "127.0.0.1:17100"
    assert (s.KAFKA_RAW_TOPIC, s.KAFKA_DLQ_TOPIC) == (
        "Property_data.raw_events",
        "Property_data.dlq_events",
    )


def test_environment_variables_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_HOST", "postgres")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    s = make()
    assert (s.POSTGRES_HOST, s.POSTGRES_PORT) == ("postgres", 5432)


def test_postgres_dsn_percent_encodes_credentials() -> None:
    s = make(POSTGRES_USER="a@b", POSTGRES_PASSWORD="p/w:x@1", POSTGRES_DB="Property_data")
    assert s.postgres_dsn == "postgresql://a%40b:p%2Fw%3Ax%401@127.0.0.1:17103/Property_data"


def test_mongo_uri_uses_admin_auth_source() -> None:
    s = make(MONGO_USER="huyhuan", MONGO_PASSWORD="se cret")
    assert s.mongo_uri == "mongodb://huyhuan:se%20cret@127.0.0.1:17102/?authSource=admin"


@pytest.mark.parametrize(
    "missing, prop",
    [({"POSTGRES_USER": ""}, "postgres_dsn"), ({"MONGO_USER": ""}, "mongo_uri")],
)
def test_dsn_requires_a_user(missing: dict[str, str], prop: str) -> None:
    with pytest.raises(ValueError, match="must be set"):
        getattr(make(**missing), prop)


def test_secrets_never_appear_in_repr() -> None:
    s = make(
        POSTGRES_PASSWORD="pg-secret", MONGO_PASSWORD="mongo-secret", TELEGRAM_BOT_TOKEN="1:tok"
    )
    text = repr(s) + str(s)
    assert "pg-secret" not in text and "mongo-secret" not in text and "1:tok" not in text


def test_raw_and_dlq_topics_must_differ() -> None:
    with pytest.raises(ValidationError, match="must be different topics"):
        make(KAFKA_RAW_TOPIC="t", KAFKA_DLQ_TOPIC="t")


@pytest.mark.parametrize(
    "overrides",
    [
        {"KAFKA_GROUP_SILVER_GOLD": "bds_bronze_mongo_groups"},
        {"KAFKA_GROUP_DLQ_WRITER": "bds_silver_gold_pg_groups"},
    ],
)
def test_pipeline_stages_need_their_own_consumer_group(overrides: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="must be different consumer groups"):
        make(**overrides)


@pytest.mark.parametrize(
    "field, value",
    [("POSTGRES_PORT", 0), ("MONGO_PORT", 70000), ("CRAWLER_LOG_LEVEL", "verbose")],
)
def test_invalid_values_are_rejected(field: str, value: Any) -> None:
    with pytest.raises(ValidationError):
        make(**{field: value})


def test_load_settings_is_cached() -> None:
    load_settings.cache_clear()
    try:
        assert load_settings() is load_settings()
    finally:
        load_settings.cache_clear()
