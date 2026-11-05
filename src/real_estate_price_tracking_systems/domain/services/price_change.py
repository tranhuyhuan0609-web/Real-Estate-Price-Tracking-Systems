"""Classify how a listing's price moved between two observations."""

from __future__ import annotations

from real_estate_price_tracking_systems.domain.value_objects.price import (
    PriceChangeEvaluation,
    PriceStatus,
)


def evaluate_price_change(
    old_price: float | None, new_price: float | None
) -> PriceChangeEvaluation:
    """Compare two prices in VND.

    A missing or non-positive *new* price means the portal shows "liên hệ" (``CONTACT``); a
    missing or non-positive *old* price means this is the first real price (``INITIAL``). The
    percentage is relative to the old price, rounded to two decimals.
    """
    if new_price is None or new_price <= 0:
        return PriceChangeEvaluation(
            price_diff_vnd=0.0, price_diff_percent=0.0, price_status=PriceStatus.CONTACT
        )
    if old_price is None or old_price <= 0:
        return PriceChangeEvaluation(
            price_diff_vnd=0.0, price_diff_percent=0.0, price_status=PriceStatus.INITIAL
        )

    diff = float(new_price) - float(old_price)
    if diff > 0:
        status = PriceStatus.INCREASED
    elif diff < 0:
        status = PriceStatus.DECREASED
    else:
        status = PriceStatus.UNCHANGED
    return PriceChangeEvaluation(
        price_diff_vnd=diff,
        price_diff_percent=round(diff / float(old_price) * 100, 2),
        price_status=status,
    )
