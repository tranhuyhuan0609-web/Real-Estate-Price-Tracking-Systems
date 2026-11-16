from datetime import datetime
from typing import Any, Protocol


class LifecycleRepository(Protocol):
    """Run progress, listing expiry and the Gold views."""

    async def get_run_progress(self, crawl_run_id: str) -> tuple[int, int] | None:
        """``(items_scraped, items_processed)``, or None for an unknown run."""
        ...

    async def get_run_details(self, crawl_run_id: str) -> dict[str, Any] | None: ...

    async def apply_lifecycle_transaction(
        self,
        site_id: str,
        started_at: datetime,
        crawl_run_id: str,
        max_missing_count: int = 3,
    ) -> dict[str, int]:
        """Expire listings of this feed that a complete sweep no longer saw."""
        ...

    async def refresh_gold_views(self) -> None: ...

    async def ensure_history_partitions(self, months_ahead: int = 2) -> int:
        """Create upcoming monthly price-history partitions; returns how many were created."""
        ...
