"""The single Settings object used by every process."""

from functools import lru_cache
from typing import Self

from pydantic import model_validator

from real_estate_price_tracking_systems.infrastructure.config.app import AppSettings
from real_estate_price_tracking_systems.infrastructure.config.database import DatabaseSettings
from real_estate_price_tracking_systems.infrastructure.config.kafka import KafkaSettings


class Settings(DatabaseSettings, KafkaSettings, AppSettings):
    """All settings groups, plus rules that span several fields."""

    @model_validator(mode="after")
    def _check_cross_field_rules(self) -> Self:
        if self.KAFKA_RAW_TOPIC == self.KAFKA_DLQ_TOPIC:
            raise ValueError("KAFKA_RAW_TOPIC and KAFKA_DLQ_TOPIC must be different topics.")
        groups = [
            self.KAFKA_GROUP_BRONZE,
            self.KAFKA_GROUP_SILVER_GOLD,
            self.KAFKA_GROUP_DLQ_WRITER,
        ]
        if len(set(groups)) != len(groups):
            # Stages sharing a group would split the topic: each would see only part of it.
            raise ValueError(
                "KAFKA_GROUP_BRONZE, KAFKA_GROUP_SILVER_GOLD and KAFKA_GROUP_DLQ_WRITER "
                "must be different consumer groups."
            )
        return self


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """Settings for this process, read once. Tests call ``load_settings.cache_clear()``."""
    return Settings()
