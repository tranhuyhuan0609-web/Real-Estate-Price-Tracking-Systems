from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from real_estate_price_tracking_systems.domain.entities import ParsedListingItem


@dataclass(frozen=True)
class ListingObservation:
    """One parsed listing as seen by one crawl run at ``event_time`` (None = now)."""

    item: ParsedListingItem
    crawl_run_id: str
    event_time: datetime | None = None
    feed: str | None = None  # the feed that saw it; defaults to item.source (the portal)


class ListingRepository(Protocol):
    """Listings, advertisers and price history."""

    async def ingest_listing_transactional(
        self,
        item: ParsedListingItem,
        crawl_run_id: str,
        update_crawl_run: bool = True,
        event_time: datetime | None = None,
        feed: str | None = None,
    ) -> tuple[bool, bool]:
        """Write one listing; returns ``(is_new, price_changed)``."""
        ...

    async def ingest_batch_transactional(
        self, batch: Sequence[ListingObservation]
    ) -> list[tuple[bool, bool]]:
        """Write a batch atomically; one ``(is_new, price_changed)`` per input, in order."""
        ...

    async def batch_update_crawl_run_metrics(
        self,
        crawl_run_id: str,
        *,
        items_processed: int,
        new_listings_count: int = 0,
        price_changes_detected: int = 0,
    ) -> None: ...
