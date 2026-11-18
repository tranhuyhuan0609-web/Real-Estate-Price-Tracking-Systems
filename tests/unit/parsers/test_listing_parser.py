"""ListingParser: mapped fields, text fallbacks, classification, address, advertiser."""

from datetime import UTC, datetime
from typing import Any

import pytest

from real_estate_price_tracking_systems.domain.entities import (
    AdvertiserKind,
    Category,
    ParsedListingItem,
    PropertyType,
)
from real_estate_price_tracking_systems.domain.value_objects import ListingKeyError
from real_estate_price_tracking_systems.infrastructure.crawler.parsing.listing_parser import (
    ListingParser as _ListingParser,
)
from real_estate_price_tracking_systems.infrastructure.crawler.parsing.phone import (
    extract_phone_from_text,
)
from real_estate_price_tracking_systems.infrastructure.crawler.parsing.road_width import (
    extract_road_width,
)
from real_estate_price_tracking_systems.infrastructure.persistence.postgres.config_mapping import (
    row_to_config,
)


class ListingParser(_ListingParser):
    """The production parser, except that an item without a url gets a placeholder one.

    ListingDetailsData rejects a blank url, and most of these tests are about other fields.
    A test that checks the url passes its own, which wins.
    """

    def parse_item(self, raw_item: dict[str, Any]) -> ParsedListingItem:
        return super().parse_item({"url": "/detail/1", **raw_item})


def test_parser_with_meeyland_sample(seed_row):

    config = row_to_config(seed_row)
    parser = ListingParser(config)

    raw_item = {
        "_id": "67223abc12345",
        "code": "307624752",
        "title": "Bán nhà Cầu Giấy 60m2 ngõ 4m sổ đỏ",
        "description": "Vị trí đẹp đường rộng 4m ô tô vào nhà, sổ đỏ chính chủ sẵn sàng giao dịch.",
        "totalPrice": 6000000000,
        "area": 60.0,
        "facade": 4.5,
        "depth": 13.3,
        "category": {"value": "mua_ban"},
        "typeOfHouse": {"value": "nha_rieng"},
        "city": {"code": "HN", "name": "Hà Nội"},
        "oldDistrict": {"code": "005", "translation": [{"name": "Cầu Giấy"}]},
        "ward": {
            "code": "00160",
            "name": "Dịch Vọng",
            "location": {"coordinates": [105.792, 21.034]},
        },
        "createdBy": {"_id": "usr_999"},
        "contact": {
            "fullName": "Nguyễn Văn A",
            "phones": ["0987654321"],
            "email": "a@example.com",
        },
        "userTypesLabel": "Môi giới",
        "publishedAt": "2026-10-30T09:30:00.000Z",
        "url": "/chi-tiet-tin-dang/307624752",
        "thumbnailDisplay": {"url": "https://img.meeyland.com/thumb.jpg"},
        "media": ["https://img.meeyland.com/1.jpg"],
    }

    parsed = parser.parse_item(raw_item)

    assert parsed.listing_key == "meeyland_307624752"
    assert parsed.category == Category.SALE
    assert parsed.property_type == PropertyType.HOUSE
    assert parsed.area_m2 == 60.0
    assert parsed.current_price_vnd == 6000000000.0
    assert parsed.current_price_per_m2 == 100000000.0
    assert parsed.details.legal_status == "Sổ đỏ/hồng chính chủ"
    assert parsed.details.district_name == "Cầu Giấy"
    assert parsed.details.lng == 105.792
    assert parsed.details.lat == 21.034
    assert parsed.advertiser.kind == AdvertiserKind.BROKER
    assert parsed.advertiser.phone == "0987654321"
    assert parsed.published_at == datetime(2026, 10, 30, 9, 30, 0, tzinfo=UTC)
    # Relative url should be converted to absolute url using base URL
    assert parsed.details.url == "https://api5.meeyland.com/chi-tiet-tin-dang/307624752"


def test_missing_id_raises_listing_key_error_instead_of_none_string(seed_row):

    config = row_to_config(seed_row)
    parser = ListingParser(config)

    # Missing both _id and code
    raw_item = {
        "_id": None,
        "code": None,
        "title": "Tin không có id",
        "url": "/detail/123",
    }
    with pytest.raises(ListingKeyError, match="either external_code or external_id is required"):
        parser.parse_item(raw_item)


def test_parser_extracts_verified_advertiser(seed_row):

    config = row_to_config(seed_row)
    parser = ListingParser(config)

    raw_item = {
        "code": 999111,
        "title": "Căn hộ Vinhomes Smart City",
        "description": "<p>Căn hộ cao cấp 2PN</p><p>Đường trước đất rộng 12m</p>",
        "url": "/du-an/vinhomes-smart-city/999111",
        "totalPrice": "3500000000",
        "area": "65",
        "createdBy": {
            "_id": "user_123",
            "phoneVerified": True,
        },
    }

    parsed = parser.parse_item(raw_item)
    assert parsed.listing_key == "meeyland_999111"
    assert parsed.advertiser.is_verified is True
    assert "<p>" not in (parsed.details.description or "")


def test_parser_extracts_media_urls_only(seed_row):

    config = row_to_config(seed_row)
    parser = ListingParser(config)

    raw_item = {
        "code": 888,
        "title": "Nhà có ảnh",
        "media": [
            {"url": "https://cdn.example.com/img1.jpg", "width": 800, "height": 600},
            {"uri": "https://cdn.example.com/img2.jpg", "mimeType": "image/jpeg"},
            "https://cdn.example.com/img3.jpg",
        ],
    }
    parsed = parser.parse_item(raw_item)
    assert parsed.details.media_list == [
        "https://cdn.example.com/img1.jpg",
        "https://cdn.example.com/img2.jpg",
        "https://cdn.example.com/img3.jpg",
    ]


def test_parser_prioritizes_contact_phone_advertiser(seed_row):

    config = row_to_config(seed_row)
    parser = ListingParser(config)

    # 1. Real phone number -> adv_{site_id}_{phone}
    raw_item = {
        "url": "/detail/1",
        "code": 111,
        "title": "Bán nhà",
        "createdBy": {"_id": "crawl_system_account_id"},
        "contact": {
            "fullName": "Nguyễn Văn A",
            "phones": ["0936.013.421"],
        },
    }
    parsed = parser.parse_item(raw_item)
    assert parsed.advertiser.advertiser_id == "adv_meeyland_0936013421"
    assert parsed.advertiser.phone == "0936013421"
    assert parsed.advertiser.name == "Nguyễn Văn A"

    # 2. System crawler phone ("0000000000") -> fallback to createdBy._id
    raw_item_bot = {
        "code": 222,
        "title": "Bán đất",
        "createdBy": {"_id": "crawl_system_account_id"},
        "contact": {
            "fullName": "Tin Bot",
            "phones": ["0000000000"],
        },
    }
    parsed_bot = parser.parse_item(raw_item_bot)
    assert parsed_bot.advertiser.advertiser_id == "crawl_system_account_id"


def test_road_width_regex_nuances(seed_row):

    # Must NOT mistakenly capture 80m2 as 80m road width!
    desc_area = "Đường trước đất, diện tích 80m2 rộng rãi thoáng mát"
    assert extract_road_width(desc_area) is None

    # Should capture "lộ giới 13m"
    desc_lo_gioi = "Nhà đẹp, lộ giới 13m ô tô quay đầu"
    assert extract_road_width(desc_lo_gioi) == 13.0

    # Should capture "lộ nhựa 6m"
    desc_lo_nhua = "Đất thổ cư mặt tiền lộ nhựa 6m"
    assert extract_road_width(desc_lo_nhua) == 6.0


def test_property_type_extended_mappings(seed_row):

    config = row_to_config(seed_row)
    parser = ListingParser(config)

    test_cases = [
        ("can_ho_chung_cu", PropertyType.APARTMENT),
        ("chung_cu_mini", PropertyType.APARTMENT),
        ("nha_mat_pho", PropertyType.HOUSE),
        ("dat_nen_du_an", PropertyType.LAND),
        ("shophouse_nha_pho_thuong_mai", PropertyType.SHOPHOUSE),
        ("biet_thu_lien_ke", PropertyType.VILLA),
        ("kho_nha_xuong", PropertyType.COMMERCIAL),
        ("khach_san_nha_nghi", PropertyType.COMMERCIAL),
    ]

    for raw_type, expected_enum in test_cases:
        raw_item = {
            "url": "/detail/1",
            "code": 12345,
            "title": f"Bán {raw_type}",
            "typeOfHouse": {"value": raw_type},
        }
        parsed = parser.parse_item(raw_item)
        assert parsed.property_type == expected_enum, (
            f"Failed for {raw_type}: got {parsed.property_type}, expected {expected_enum}"
        )


def test_parser_dimension_fallback(seed_row):

    config = row_to_config(seed_row)
    parser = ListingParser(config)

    # Case 1: facade_m and depth_m not in raw payload, extracted from title
    item = parser.parse_item(
        {
            "code": 9991,
            "title": "Bán nhà 5x20m đường ô tô tránh",
            "description": "Nhà đẹp chính chủ",
        }
    )
    assert item.facade_m == 5.0
    assert item.depth_m == 20.0

    # Case 2: facade_m and depth_m explicitly in payload, not overridden
    item2 = parser.parse_item(
        {
            "code": 9992,
            "title": "Bán nhà 5x20m đường ô tô tránh",
            "facade": 6.5,
            "depth": 22.0,
        }
    )
    assert item2.facade_m == 6.5
    assert item2.depth_m == 22.0


def test_extract_phone_and_email_fallback(seed_row):
    from real_estate_price_tracking_systems.infrastructure.persistence.postgres.config_mapping import (
        row_to_config,
    )

    assert extract_phone_from_text("Liên hệ chính chủ: 0932.068.012") == "0932068012"
    assert extract_phone_from_text("Zalo 090 123 4567") == "0901234567"
    assert extract_phone_from_text("Không có sđt") is None

    config = row_to_config(seed_row)
    parser = ListingParser(config)

    # Item with phone and email embedded inside description only
    item = parser.parse_item(
        {
            "code": 12345,
            "title": "Bán nhà Tân Bình",
            "description": "Nhà đẹp chính chủ. Alo ngay 0988.999.888 gặp Nam. Email: nam.bds@gmail.com",
        }
    )
    assert item.advertiser is not None
    assert item.advertiser.phone == "0988999888"
    assert item.advertiser.email == "nam.bds@gmail.com"


def test_mapping_precedence_over_same_named_raw_keys(seed_row):
    import copy

    from real_estate_price_tracking_systems.infrastructure.persistence.postgres.config_mapping import (
        row_to_config,
    )

    row = copy.deepcopy(seed_row)
    # Map category to raw field 'type'
    row["config_json"]["response_mapping"]["fields"]["category"] = "type"
    row["config_json"]["response_mapping"]["value_mappings"]["category"] = {
        "s": "sale",
        "u": "rent",
        "_default": "sale",
    }
    config = row_to_config(row)
    parser = ListingParser(config)

    # Raw item contains both a raw key named 'category' (e.g. 1050) AND 'type' ('u')
    item = parser.parse_item(
        {
            "code": 9999,
            "title": "Cho thuê phòng trọ",
            "category": 1050,  # Must NOT override the mapped path 'type'
            "type": "u",  # Must be mapped to 'rent'
        }
    )
    assert item.category == Category.RENT


def test_parser_extracts_external_id_from_urls_with_ward_slugs(seed_row):
    import copy

    from real_estate_price_tracking_systems.infrastructure.persistence.postgres.config_mapping import (
        row_to_config,
    )

    # Test Mogi URL containing ward slug "-p10-go-vap-id22749307"
    mogi_row = copy.deepcopy(seed_row)
    mogi_row["site_id"] = "mogi"
    mogi_row["config_json"]["response_mapping"]["value_mappings"] = {}
    mogi_row["config_json"]["response_mapping"]["fields"] = {
        "external_id": "url",
        "url": "url",
        "title": "title",
    }
    config = row_to_config(mogi_row)
    parser = ListingParser(config)

    item = parser.parse_item(
        {
            "url": "https://mogi.vn/quan-go-vap/mua-nha-mat-tien-pho/ban-nha-mat-tien-3-tang-6-5x40-tien-265-nguyen-van-luong-p10-go-vap-id22749307",
            "title": "Bán nhà mặt tiền 3 tầng Nguyễn Văn Lượng p10",
            "totalPrice": "45000000000",
            "area": "256",
        }
    )
    assert item.external_id == "22749307"
    assert item.listing_key == "mogi_22749307"

    # Test bds_com_vn URL with -p<id>.html
    bds_row = copy.deepcopy(seed_row)
    bds_row["site_id"] = "bds_com_vn"
    bds_row["config_json"]["response_mapping"]["value_mappings"] = {}
    bds_row["config_json"]["response_mapping"]["fields"] = {
        "external_id": "url",
        "url": "url",
        "title": "title",
    }
    bds_config = row_to_config(bds_row)
    bds_parser = ListingParser(bds_config)
    bds_item = bds_parser.parse_item(
        {
            "url": "https://bds.com.vn/view-cao-thoang-p519188.html",
            "title": "View cao thoáng",
            "totalPrice": "1000000000",
            "area": "100",
        }
    )
    assert bds_item.external_id == "519188"
    assert bds_item.listing_key == "bds_com_vn_519188"


def test_infer_property_type_and_category_fallbacks(seed_row):
    import copy

    from real_estate_price_tracking_systems.infrastructure.persistence.postgres.config_mapping import (
        row_to_config,
    )

    row = copy.deepcopy(seed_row)
    row["config_json"]["response_mapping"]["value_mappings"] = {}
    row["config_json"]["response_mapping"]["fields"] = {
        "external_id": "url",
        "url": "url",
        "title": "title",
        "advertiser_name": "contact_name",
    }
    config = row_to_config(row)
    parser = ListingParser(config)

    # 1. Apartment rent
    it1 = parser.parse_item(
        {
            "url": "/cho-thue-can-ho-chung-cu-vinhomes-id101",
            "title": "Cho thuê căn hộ chung cư 2PN",
            "totalPrice": "15000000",
            "area": "70",
            "contact_name": "Trần Thị Mai",
        }
    )
    assert it1.property_type == PropertyType.APARTMENT
    assert it1.category == Category.RENT
    assert it1.advertiser.name == "Trần Thị Mai"
    assert it1.advertiser.advertiser_id.startswith("adv_meeyland_")

    # 2. Commercial
    it2 = parser.parse_item(
        {
            "url": "/cho-thue-van-phong-duy-tan-id102",
            "title": "Cho thuê mặt bằng kinh doanh văn phòng",
            "totalPrice": "25000000",
            "area": "120",
        }
    )
    assert it2.property_type == PropertyType.COMMERCIAL
    assert it2.category == Category.RENT

    # 3. Land sale
    it3 = parser.parse_item(
        {
            "url": "/ban-dat-nen-tho-cu-id103",
            "title": "Bán đất thổ cư 100m2",
            "totalPrice": "2000000000",
            "area": "100",
        }
    )
    assert it3.property_type == PropertyType.LAND
    assert it3.category == Category.SALE

    # 4. Villa
    it4 = parser.parse_item(
        {
            "url": "/ban-biet-thu-vinhomes-id104",
            "title": "Bán biệt thự song lập",
            "totalPrice": "30000000000",
            "area": "250",
        }
    )
    assert it4.property_type == PropertyType.VILLA
    assert it4.category == Category.SALE


def test_category_rental_title_override(seed_row):

    config = row_to_config(seed_row)
    parser = ListingParser(config)

    # Title explicitly says "cho thuê" but category was mapped to sale
    raw_item = {
        "url": "/detail/1",
        "code": 999,
        "title": "Top nhà phố cho thuê vị trí đẹp trung tâm Q1",
        "category": {"value": "mua_ban"},  # Mapped to sale by default
    }
    parsed = parser.parse_item(raw_item)
    assert parsed.category == Category.RENT


def test_vietnam_coordinates_bounding_box(seed_row):

    config = row_to_config(seed_row)
    parser = ListingParser(config)

    # Coordinates in Central Africa (lat=10.0, lng=23.0) -> should be discarded
    raw_item_africa = {
        "code": 1001,
        "title": "Bán nhà đẹp",
        "lat": 10.0,
        "lng": 23.0,
    }
    parsed_africa = parser.parse_item(raw_item_africa)
    assert parsed_africa.details.lat is None
    assert parsed_africa.details.lng is None

    # Valid coordinates in Vietnam (HCMC: ~10.77, ~106.69)
    raw_item_vn = {
        "code": 1002,
        "title": "Bán nhà đẹp",
        "lat": 10.77,
        "lng": 106.69,
    }
    parsed_vn = parser.parse_item(raw_item_vn)
    assert parsed_vn.details.lat == 10.77
    assert parsed_vn.details.lng == 106.69


def test_unmask_email_from_description_when_field_masked(seed_row):
    from real_estate_price_tracking_systems.infrastructure.persistence.postgres.config_mapping import (
        row_to_config,
    )

    config = row_to_config(seed_row)
    parser = ListingParser(config)

    # Item where structured contact.email is masked with *, but description contains real unmasked email
    item = parser.parse_item(
        {
            "code": 8888,
            "title": "Bán nhà quận 1 chính chủ",
            "contact": {
                "fullName": "Nguyễn Hoàng",
                "phones": ["0903123456"],
                "email": "hoang***@gmail.com",
            },
            "description": "Bán gấp nhà trung tâm Q1. Liên hệ chính chủ qua email: hoang.bds.q1@gmail.com hoặc SĐT 0903.123.456",
        }
    )

    assert item.advertiser is not None
    assert item.advertiser.phone == "0903123456"
    # Masked 'hoang***@gmail.com' was unmasked and replaced by 'hoang.bds.q1@gmail.com' from description!
    assert item.advertiser.email == "hoang.bds.q1@gmail.com"
