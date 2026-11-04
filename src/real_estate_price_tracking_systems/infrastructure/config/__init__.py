"""Typed application settings read from the environment and the repository `.env`."""

from real_estate_price_tracking_systems.infrastructure.config.settings import (
    Settings,
    load_settings,
)

__all__ = ["Settings", "load_settings"]
