"""Price status and the result of comparing two observed prices."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class PriceStatus(StrEnum):
    INITIAL = "initial"  # first known price
    INCREASED = "increased"
    DECREASED = "decreased"
    UNCHANGED = "unchanged"
    CONTACT = "contact"  # no price shown ("liên hệ")


class PriceChangeEvaluation(BaseModel):
    """Difference between the previous and the new price of a listing."""

    model_config = ConfigDict(frozen=True)

    price_diff_vnd: float
    price_diff_percent: float
    price_status: PriceStatus
