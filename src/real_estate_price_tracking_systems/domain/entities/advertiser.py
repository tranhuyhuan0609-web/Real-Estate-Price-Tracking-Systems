"""The person or agency that posted a listing."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class AdvertiserKind(StrEnum):
    BROKER = "broker"
    OWNER = "owner"
    UNKNOWN = "unknown"


class AdvertiserData(BaseModel):
    """Advertiser as extracted from a listing. Every field is optional: portals mask phones."""

    advertiser_id: str | None = None
    name: str | None = None
    phone: str | None = None
    email: str | None = None
    kind: AdvertiserKind = AdvertiserKind.UNKNOWN
    is_verified: bool = False
