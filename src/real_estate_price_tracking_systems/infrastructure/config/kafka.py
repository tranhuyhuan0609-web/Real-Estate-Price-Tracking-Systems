"""Kafka connection, topic and consumer-group settings."""

from pydantic import Field

from real_estate_price_tracking_systems.infrastructure.config.base import BaseSubSettings


class KafkaSettings(BaseSubSettings):
    """Defaults match docker compose and docs/naming.md.

    One consumer group per pipeline stage: each stage must receive every event, so two stages
    sharing a group would split the topic between them (validated in Settings).
    """

    KAFKA_BOOTSTRAP_SERVERS: str = Field(default="127.0.0.1:17100", min_length=1)
    KAFKA_RAW_TOPIC: str = Field(default="Property_data.raw_events", min_length=1)
    KAFKA_DLQ_TOPIC: str = Field(default="Property_data.dlq_events", min_length=1)

    KAFKA_GROUP_BRONZE: str = Field(default="bds_bronze_mongo_groups", min_length=1)
    KAFKA_GROUP_SILVER_GOLD: str = Field(default="bds_silver_gold_pg_groups", min_length=1)
    KAFKA_GROUP_DLQ_WRITER: str = Field(default="bds_dlq_writer_groups", min_length=1)
