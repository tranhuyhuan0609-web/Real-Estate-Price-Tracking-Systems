"""Shared pydantic-settings configuration for every settings group."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# src/<package>/infrastructure/config/base.py -> repository root
BASE_DIR = Path(__file__).resolve().parents[4]


class BaseSubSettings(BaseSettings):
    """Base for settings groups.

    Values come from environment variables first (how containers configure the services), then
    from ``<repo>/.env`` (local development). The path is absolute, so tools started from any
    working directory read the same file. Unknown keys are ignored so one ``.env`` can serve
    every group and docker compose.
    """

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
        validate_default=True,
    )
