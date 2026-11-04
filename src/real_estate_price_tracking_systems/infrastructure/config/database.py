"""Connection settings for PostgreSQL (Silver/Gold) and MongoDB (Bronze)."""

from urllib.parse import quote

from pydantic import Field, SecretStr

from real_estate_price_tracking_systems.infrastructure.config.base import BaseSubSettings


class DatabaseSettings(BaseSubSettings):
    """Defaults target the ports docker compose publishes on the host (docs/naming.md)."""

    # MongoDB: Bronze raw payloads and the DLQ archive
    MONGO_HOST: str = "127.0.0.1"
    MONGO_PORT: int = Field(default=17102, ge=1, le=65535)
    MONGO_USER: str = ""
    MONGO_PASSWORD: SecretStr = SecretStr("")
    MONGO_DB: str = "Property_data"

    # PostgreSQL + PostGIS: Silver listings and Gold price history
    POSTGRES_HOST: str = "127.0.0.1"
    POSTGRES_PORT: int = Field(default=17103, ge=1, le=65535)
    POSTGRES_USER: str = ""
    POSTGRES_PASSWORD: SecretStr = SecretStr("")
    POSTGRES_DB: str = "Property_data"

    @property
    def postgres_dsn(self) -> str:
        """libpq URL with user, password and database percent-encoded."""
        if not self.POSTGRES_USER or not self.POSTGRES_DB:
            raise ValueError("POSTGRES_USER and POSTGRES_DB must be set.")
        user = quote(self.POSTGRES_USER, safe="")
        password = quote(self.POSTGRES_PASSWORD.get_secret_value(), safe="")
        database = quote(self.POSTGRES_DB, safe="")
        return (
            f"postgresql://{user}:{password}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{database}"
        )

    @property
    def mongo_uri(self) -> str:
        """URI authenticating against ``admin``, where the image creates the root user."""
        if not self.MONGO_USER:
            raise ValueError("MONGO_USER must be set.")
        user = quote(self.MONGO_USER, safe="")
        password = quote(self.MONGO_PASSWORD.get_secret_value(), safe="")
        return f"mongodb://{user}:{password}@{self.MONGO_HOST}:{self.MONGO_PORT}/?authSource=admin"
