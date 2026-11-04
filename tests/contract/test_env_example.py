"""`.env.example` must document exactly what Settings reads, plus the compose-only variables."""

from pathlib import Path

from real_estate_price_tracking_systems.infrastructure.config.settings import Settings

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"

# Read by docker compose only (host port mapping), never by the application.
COMPOSE_ONLY = {"KAFKA_HOST_PORT", "KAFKA_UI_HOST_PORT", "MONGO_HOST_PORT", "POSTGRES_HOST_PORT"}


def example_keys() -> set[str]:
    keys: set[str] = set()
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            keys.add(line.split("=", 1)[0].strip())
    return keys


def test_env_example_documents_every_setting() -> None:
    missing = set(Settings.model_fields) - example_keys()
    assert not missing, f"read by Settings but missing from .env.example: {sorted(missing)}"


def test_env_example_has_no_unused_variables() -> None:
    unused = example_keys() - set(Settings.model_fields) - COMPOSE_ONLY
    assert not unused, f"in .env.example but read by nothing: {sorted(unused)}"


def test_env_example_contains_no_real_secrets() -> None:
    values = dict(
        line.split("=", 1)
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )
    for key in ("POSTGRES_PASSWORD", "MONGO_PASSWORD", "TELEGRAM_BOT_TOKEN"):
        assert values.get(key, "") in ("", "change_me"), f"{key} must be a placeholder"
