"""Turn one raw API/HTML item into a :class:`ParsedListingItem` using ``response_mapping``."""

import re
from typing import Any
from urllib.parse import urljoin

from real_estate_price_tracking_systems.domain.entities import (
    Category,
    CrawlerConfig,
    ListingDetailsData,
    ParsedListingItem,
    PropertyType,
)
from real_estate_price_tracking_systems.domain.location import parse_vietnamese_address
from real_estate_price_tracking_systems.domain.location.administrative_data import (
    KNOWN_HANOI_DISTRICT_NAMES,
    KNOWN_HCM_DISTRICT_NAMES,
)
from real_estate_price_tracking_systems.domain.services import generate_fingerprint
from real_estate_price_tracking_systems.domain.value_objects import build_listing_key
from real_estate_price_tracking_systems.infrastructure.crawler.parsing.area import (
    extract_dimensions,
    parse_vietnamese_area,
)
from real_estate_price_tracking_systems.infrastructure.crawler.parsing.datetime_parser import (
    parse_vietnamese_datetime,
)
from real_estate_price_tracking_systems.infrastructure.crawler.parsing.html_cleaner import (
    clean_html,
)
from real_estate_price_tracking_systems.infrastructure.crawler.parsing.json_path import (
    extract_by_json_path,
)
from real_estate_price_tracking_systems.infrastructure.crawler.parsing.legal_status import (
    extract_legal_status,
)
from real_estate_price_tracking_systems.infrastructure.crawler.parsing.numbers import (
    safe_float,
    safe_int,
)
from real_estate_price_tracking_systems.infrastructure.crawler.parsing.price import (
    parse_vietnamese_price,
)

RawItem = dict[str, Any]


def infer_property_type(text: str) -> PropertyType:
    """Infer property type from listing title, breadcrumbs or URL slug if not explicitly mapped."""
    t = text.lower()
    if (
        re.search(
            r"\b(căn hộ|can ho|chung cư|chung cu|ccmn|chcc|penthouse|duplex|officetel|tập thể|tap the|[1-5]\s*pn|phòng ngủ)\b",
            t,
        )
        or "-can-ho-" in t
        or "-chung-cu-" in t
        or "/can-ho-" in t
        or "/chung-cu-" in t
    ):
        return PropertyType.APARTMENT
    if (
        re.search(r"\b(biệt thự|biet thu|villa|dinh thự|dinh thu)\b", t)
        or "-biet-thu-" in t
        or "-villa-" in t
        or "/biet-thu-" in t
    ):
        return PropertyType.VILLA
    if (
        re.search(r"\b(shophouse|nhà phố thương mại|nha pho thuong mai)\b", t)
        or "-shophouse-" in t
        or "/shophouse-" in t
    ):
        return PropertyType.SHOPHOUSE
    if (
        re.search(
            r"\b(kho|xưởng|nhà xưởng|văn phòng|van phong|mặt bằng|mat bang|khách sạn|hotel|resort|kios|ki-ốt|tmdv|thương mại dịch vụ|sàn chân đế)\b",
            t,
        )
        or "-kho-" in t
        or "-xuong-" in t
        or "-van-phong-" in t
        or "-mat-bang-" in t
    ):
        return PropertyType.COMMERCIAL
    if (
        re.search(
            r"\b(đất|dat|đất nền|dat nen|thổ cư|tho cu|lô đất|lo dat|mảnh đất|thửa đất|lô góc|lo goc|vườn|sào|hecta|ha)\b",
            t,
        )
        or "-dat-" in t
        or "-dat-nen-" in t
        or "/ban-dat" in t
    ):
        return PropertyType.LAND
    if (
        re.search(
            r"\b(nhà|nha|nhà riêng|nha rieng|nhà phố|nha pho|nhà mặt tiền|nha mat tien|nhà hẻm|nha hem|nhà ngõ|nha ngo|nhà cấp 4|liền kề|lien ke|hxh|hxt|bán nr|\bnr\b|\d+\s*tầng)\b",
            t,
        )
        or "-nha-" in t
        or "/ban-nha" in t
    ):
        return PropertyType.HOUSE
    return PropertyType.OTHER


_CITY_URL_HINTS = (
    (("ho-chi-minh", "tphcm", "tp-hcm"), "Thành phố Hồ Chí Minh"),
    (("ha-noi", "hanoi"), "Thành phố Hà Nội"),
    (("da-nang", "danang"), "Thành phố Đà Nẵng"),
    (("binh-duong", "binhduong"), "Tỉnh Bình Dương"),
    (("dong-nai", "dongnai"), "Tỉnh Đồng Nai"),
)


def infer_city(url: str, district_name: str | None) -> str | None:
    """Last-resort city guess from URL slugs, then from well-known HCM / Hà Nội district names."""
    url_lower = (url or "").lower()
    for hints, city in _CITY_URL_HINTS:
        if any(hint in url_lower for hint in hints):
            return city
    district = (district_name or "").lower()
    if district:
        if any(name in district for name in KNOWN_HCM_DISTRICT_NAMES):
            return "Thành phố Hồ Chí Minh"
        if any(name in district for name in KNOWN_HANOI_DISTRICT_NAMES):
            return "Thành phố Hà Nội"
    return None


def infer_category(text: str) -> Category:
    """Infer transaction category (sale/rent/project) from title or URL slug if not mapped."""
    t = text.lower()
    if (
        re.search(r"\b(cho thuê|cho thue|thuê|thue)\b", t)
        or "/cho-thue-" in t
        or "/thue-" in t
        or "-cho-thue-" in t
    ):
        return Category.RENT
    if re.search(r"\b(dự án|du an)\b", t) or "/du-an-" in t or "-du-an-" in t:
        return Category.PROJECT
    return Category.SALE


class ListingParser:
    """Parses raw records into the domain's :class:`ParsedListingItem`.

    Field locations come from the feed's ``response_mapping.fields`` (dotted JSON paths for APIs,
    selectors already resolved to values for HTML feeds); a field with no mapping falls back to a
    key of the same name in the item.
    """

    def __init__(self, config: CrawlerConfig) -> None:
        self.config = config
        self.mapping = config.response_mapping
        self.fields = self.mapping.fields

    def _extract_val(self, raw_item: RawItem, field_name: str) -> Any:
        """Mapped path first, then a key of the same name, else None."""
        path = self.fields.get(field_name, "")
        if path:
            val = extract_by_json_path(raw_item, path)
            if val is not None:
                return val
        return raw_item.get(field_name)

    def _text(self, raw_item: RawItem, field: str) -> str:
        return str(self._extract_val(raw_item, field) or "").strip()

    def parse_item(self, raw_item: RawItem) -> ParsedListingItem:
        """Parse one raw listing according to the feed's configuration."""
        external_id, external_code = self._external_ids(raw_item)
        listing_key = build_listing_key(
            self.config.portal_id, external_code=external_code, external_id=external_id
        )

        title = self._text(raw_item, "title")
        description = self._extract_val(raw_item, "description")
        description_str = clean_html(str(description)) if description is not None else None
        text_context = f"{title} {description_str or ''}"

        area_m2 = parse_vietnamese_area(self._extract_val(raw_item, "area_m2"))
        price_vnd, price_per_m2 = self._price(raw_item, area_m2)
        facade_m, depth_m = self._dimensions(raw_item, text_context)
        category, property_type = self._classify(raw_item, title)

        url = self._url(raw_item, external_id, external_code)
        lat, lng = self._coordinates(raw_item)
        address = self._address(raw_item, url)
        details = ListingDetailsData(
            url=url,
            title=title,
            description=description_str,
            city_name=address["city_name"],
            district_name=address["district_name"],
            ward_name=address["ward_name"],
            lng=lng,
            lat=lat,
            legal_status=self._legal_status(raw_item, description_str),
            thumbnail_url=self._extract_val(raw_item, "thumbnail_url"),
            media_list=self._extract_val(raw_item, "media_list"),
        )
        return ParsedListingItem(
            listing_key=listing_key,
            source=self.config.portal_id,
            external_id=external_id,
            external_code=external_code,
            property_fingerprint=generate_fingerprint(
                title=title,
                area_m2=area_m2,
                city_name=details.city_name,
                district_name=details.district_name,
                ward_name=details.ward_name,
            ),
            category=category,
            property_type=property_type,
            area_m2=area_m2,
            facade_m=facade_m,
            depth_m=depth_m,
            current_price_vnd=price_vnd,
            current_price_per_m2=price_per_m2,
            published_at=parse_vietnamese_datetime(
                self._extract_val(raw_item, "published_at"),
                default_tz=self.config.content_zoneinfo(),
            ),
            details=details,
        )

    # ------------------------------------------------------------------ steps
    def _external_ids(self, raw_item: RawItem) -> tuple[str | None, int | None]:
        raw_id = self._extract_val(raw_item, "external_id")
        external_id = str(raw_id).strip() if raw_id is not None and str(raw_id).strip() else None
        external_code = safe_int(self._extract_val(raw_item, "external_code"))
        return clean_external_id(external_id), external_code

    def _price(self, raw_item: RawItem, area_m2: float | None) -> tuple[float | None, float | None]:
        """Whole-dong total and per-m2 price; per-m2 is derived when the text only gave a total."""
        price_vnd, per_m2 = parse_vietnamese_price(
            self._extract_val(raw_item, "price_vnd"), area_m2
        )
        if price_vnd is not None:
            price_vnd = float(round(price_vnd))
        if per_m2 is not None:
            per_m2 = float(round(per_m2))
        elif price_vnd and area_m2 and area_m2 > 0:
            per_m2 = float(round(price_vnd / area_m2, 0))
        return price_vnd, per_m2

    def _dimensions(
        self, raw_item: RawItem, text_context: str
    ) -> tuple[float | None, float | None]:
        """Facade and depth: mapped fields win, the title and description fill the gaps."""
        facade = positive(safe_float(self._extract_val(raw_item, "facade_m")))
        depth = positive(safe_float(self._extract_val(raw_item, "depth_m")))
        if facade is None or depth is None:
            facade_text, depth_text = extract_dimensions(text_context)
            facade = facade if facade is not None else facade_text
            depth = depth if depth is not None else depth_text
        return facade, depth

    def _legal_status(self, raw_item: RawItem, description: str | None) -> str | None:
        """The mapped legal status, else a keyword match in the description (max 50 chars)."""
        raw = self._extract_val(raw_item, "legal_status")
        if raw is not None and str(raw).strip():
            status: str | None = self._map_enum_value("legal_status", raw, str(raw).strip())
        else:
            status = extract_legal_status(description)
        return status[:50] if status else None

    def _coordinates(self, raw_item: RawItem) -> tuple[float | None, float | None]:
        """``(lat, lng)``, or ``(None, None)`` when the pair falls outside Vietnam."""
        lat = safe_float(self._extract_val(raw_item, "lat"))
        lng = safe_float(self._extract_val(raw_item, "lng"))
        if (
            lat is not None
            and lng is not None
            and not (8.0 <= lat <= 24.0 and 102.0 <= lng <= 110.5)
        ):
            return None, None  # a swapped or zeroed pair would put the listing in the sea
        return lat, lng

    def _address(self, raw_item: RawItem, url: str) -> dict[str, str | None]:
        """Structured address from the raw address and the portal's own hints.

        When no city comes out, it is guessed from the URL slug, then from well-known district
        names (``infer_city``).
        """

        def hint(field: str) -> str | None:
            value = self._extract_val(raw_item, field)
            return str(value).strip() if value else None

        parts = parse_vietnamese_address(
            raw_address=hint("address"),
            city_hint=hint("city_name"),
            district_hint=hint("district_name"),
            ward_hint=hint("ward_name"),
        )
        if not parts.get("city_name"):
            parts["city_name"] = infer_city(url, parts.get("district_name"))
        return parts

    def _map_enum_value(self, field_name: str, raw_value: Any, default: str) -> str:
        """Translate a source value through ``value_mappings`` (``_default`` is the catch-all)."""
        if raw_value is None:
            return default
        value = str(raw_value).strip()
        mapping = self.mapping.value_mappings.get(field_name, {})
        return mapping.get(value, mapping.get("_default", value))

    def _classify(self, raw_item: RawItem, title: str) -> tuple[Category, PropertyType]:
        """Category and property type: the mapped value when valid, else inferred from the text."""
        hint = f"{title} {self._text(raw_item, 'breadcrumb')} {self._text(raw_item, 'url')}"

        category: Category | None = None
        raw_category = self._extract_val(raw_item, "category")
        if raw_category is not None:
            try:
                category = Category(
                    self._map_enum_value("category", raw_category, Category.SALE.value)
                )
            except ValueError:
                category = None
        if category is None:
            category = infer_category(hint)
        # A title that says "cho thuê" (and not "bán") is a rental whatever the source category says.
        title_lower = title.lower()
        if (
            category == Category.SALE
            and re.search(r"\b(cho thuê|cho thue)\b", title_lower)
            and not re.search(r"\b(bán|ban)\b", title_lower)
        ):
            category = Category.RENT

        property_type = PropertyType.OTHER
        raw_type = self._extract_val(raw_item, "property_type")
        if raw_type is not None:
            try:
                property_type = PropertyType(
                    self._map_enum_value("property_type", raw_type, PropertyType.OTHER.value)
                )
            except ValueError:
                property_type = PropertyType.OTHER
        if property_type == PropertyType.OTHER:
            property_type = infer_property_type(hint)
        return category, property_type

    def _url(self, raw_item: RawItem, external_id: str | None, external_code: int | None) -> str:
        """The item's own URL (made absolute), else ``url_template``, else empty.

        An empty URL is rejected by ``ListingDetailsData``, so a feed that gives neither is
        reported per item instead of storing a listing nobody can open.
        """
        raw_url = self._text(raw_item, "url")
        if raw_url:
            return urljoin(str(self.config.request.url), raw_url)
        if self.mapping.url_template and (external_id or external_code):
            return self.mapping.url_template.format(
                external_id=external_id or "", external_code=external_code or ""
            )
        return ""


# ---------------------------------------------------------------------- helpers
_EXTERNAL_ID_IN_URL = re.compile(
    r"-id(\d+)(?:[/?#]|$)|-es(\d+)(?:[/?#]|$)|-p(\d+)\.html|-(\d+)\.html|/(\d+)(?:\.htm)?(?:[/?#]|$)"
)


def clean_external_id(external_id: str | None) -> str | None:
    """Pull the numeric id out of a listing URL ("...-id22756927", "...-es123", "...-3191063.html")."""
    if not external_id or not any(
        token in external_id for token in ("/", "-id", "-es", "-p", ".html", ".htm")
    ):
        return external_id
    match = _EXTERNAL_ID_IN_URL.search(external_id)
    if not match:
        return external_id
    return next(group for group in match.groups() if group)


def positive(value: float | None) -> float | None:
    return value if value is not None and value > 0 else None
