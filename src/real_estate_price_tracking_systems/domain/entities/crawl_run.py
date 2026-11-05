"""One execution of a spider against one site."""

from __future__ import annotations

from enum import StrEnum


class RunMode(StrEnum):
    INCREMENTAL = "incremental"  # newest pages only, stops early
    FULL_SWEEP = "full_sweep"  # every page; only a complete sweep may expire listings


class CrawlRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
