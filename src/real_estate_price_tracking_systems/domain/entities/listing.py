"""Listings as produced by spiders and carried on the raw-events topic."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from real_estate_price_tracking_systems.domain.entities.advertiser import AdvertiserData
from real_estate_price_tracking_systems.domain.entities.base import NonBlank


class Category(StrEnum):
    SALE = "sale"
    RENT = "rent"
    PROJECT = "project"


class PropertyType(StrEnum):
    LAND = "land"
    HOUSE = "house"
    APARTMENT = "apartment"
    VILLA = "villa"
    SHOPHOUSE = "shophouse"
    COMMERCIAL = "commercial"
    OTHER = "other"


class ListingStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    HIDDEN = "hidden"


class PriceStatus(StrEnum):
    INITIAL = "initial"
    INCREASED = "increased"
    DECREASED = "decreased"
    UNCHANGED = "unchanged"
    CONTACT = "contact"  # no price shown ("liên hệ")


class ListingDetailsData(BaseModel):
    """Descriptive, geospatial and legal details of a listing.

    ``extra="ignore"``: portals add fields all the time, and an unknown one must not send the
    whole listing to the DLQ.
    """

    model_config = ConfigDict(extra="ignore")

    url: NonBlank
    title: NonBlank
    description: str | None = None
    city_name: str | None = None
    district_name: str | None = None
    ward_name: str | None = None
    lng: float | None = None
    lat: float | None = None
    legal_status: str | None = None
    thumbnail_url: str | None = None
    media_list: list[str] | None = None

    @field_validator("media_list", mode="before")
    @classmethod
    def _coerce_media_list(cls, value: Any) -> list[str] | None:
        """Accept plain URLs or ``{"url"|"uri"|"src": ...}`` objects; drop blanks."""
        if not value or not isinstance(value, list):
            return None
        urls: list[str] = []
        for item in value:
            if isinstance(item, dict):
                item = item.get("url") or item.get("uri") or item.get("src")
            if isinstance(item, str) and item.strip():
                urls.append(item.strip())
        return urls or None


class ParsedListingItem(BaseModel):
    """A listing in the shape every spider produces, whatever the portal."""

    listing_key: NonBlank
    source: NonBlank
    external_id: str | None = None
    external_code: int | None = None
    property_fingerprint: str | None = None
    category: Category = Category.SALE
    property_type: PropertyType = PropertyType.OTHER
    area_m2: float | None = None
    facade_m: float | None = None
    depth_m: float | None = None
    current_price_vnd: float | None = None
    current_price_per_m2: float | None = None
    published_at: datetime | None = None
    details: ListingDetailsData
    advertiser: AdvertiserData | None = None


class RawEventMessage(BaseModel):
    """Message on the raw-events topic: the parsed listing plus the untouched portal payload,
    so Bronze can be replayed through a fixed parser later."""

    model_config = ConfigDict(extra="ignore")

    listing_key: NonBlank
    site_id: NonBlank
    crawl_run_id: NonBlank
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    parsed_data: ParsedListingItem
    raw_payload: dict[str, Any]
