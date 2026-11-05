"""Property fingerprint: the same property posted on several sites gets the same value."""

from __future__ import annotations

import hashlib
import re

_PUNCTUATION = re.compile(r"[^\w\s]")


def _norm(text: str | None) -> str:
    return " ".join((text or "").lower().split())


def generate_fingerprint(
    *,
    title: str,
    area_m2: float | None = None,
    city_name: str | None = None,
    district_name: str | None = None,
    ward_name: str | None = None,
) -> str:
    """SHA-256 (hex) of the normalised title, area and ward/district/city.

    Case, punctuation and extra whitespace are ignored; the area is rounded to 0.1 m². Phone
    and price are deliberately not inputs: revealing a masked phone or changing the price must
    not turn the listing into a different property.
    """
    area = f"{round(area_m2, 1)}" if area_m2 and area_m2 > 0 else ""
    parts = (
        _norm(_PUNCTUATION.sub("", title)),
        area,
        *map(_norm, (city_name, district_name, ward_name)),
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
