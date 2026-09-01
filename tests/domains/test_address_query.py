"""주소 검색어 전처리 SSOT 계약 (GEO-QUERY-01).

운영 사고(2026-08-31, 주문 5062): DB 주소가 `오산역금강펜테리움1103-301` 처럼 공백
없이 저장돼 있었는데, 동호수 제거 정규식이 모두 앞 공백(``\\s+``)을 요구해서 후보가
원본 1개뿐이었다. 모달 검색도 워커 지오코딩도 똑같이 0건이었고 `geocode_status` 는
`failed` 로 남았다. 카카오 실호출 확인: `오산역금강펜테리움` 은 keyword API 에서
정상 조회된다(경기 오산시 가수동 449).
"""
from __future__ import annotations

from foms.services.common.address_query import query_variants, strip_detail


def test_strips_attached_dong_ho_without_space() -> None:
    """붙여쓴 ``NNN-NNN`` 동호수를 떼어낸다(회귀 고정)."""
    assert strip_detail("오산역금강펜테리움1103-301") == "오산역금강펜테리움"
    assert "오산역금강펜테리움" in query_variants("오산역금강펜테리움1103-301")


def test_keeps_jibun_that_looks_like_dong_ho() -> None:
    """지번 ``2287-15`` 는 뒷자리가 3자리 미만이라 보존한다."""
    assert strip_detail("동패동 2287-15") == "동패동 2287-15"
    assert query_variants("동패동 2287-15")[0] == "동패동 2287-15"


def test_road_address_keeps_building_number() -> None:
    """도로명 주소는 건물번호까지만 남긴다."""
    assert strip_detail("경기 의왕시 시청로 42 108-1701") == "경기 의왕시 시청로 42"


def test_dong_ho_and_ho_only_tails() -> None:
    assert strip_detail("잠실 르엘 101동 1502호") == "잠실 르엘"
    assert strip_detail("잠실르엘101동1502호") == "잠실르엘"
    assert strip_detail("삼성래미안 1502호") == "삼성래미안"


def test_comma_detail_removed() -> None:
    assert strip_detail("경기 평택시 화양현화2로 45, e편한세상 102-2002") == "경기 평택시 화양현화2로 45"


def test_variants_are_deduped_and_original_first() -> None:
    variants = query_variants("오산역 금강펜테리움 1103-301")
    assert variants[0] == "오산역 금강펜테리움 1103-301"
    assert len(variants) == len(set(variants))
    assert "오산역 금강펜테리움" in variants


def test_empty_input_is_safe() -> None:
    assert strip_detail("") == ""
    assert query_variants("") == []
    assert query_variants(None) == []


def test_modal_and_geocode_pipeline_share_the_same_preprocessing() -> None:
    """모달 검색과 워커 지오코딩이 같은 전처리를 쓴다(2벌 재분기 방지)."""
    from foms.api.address import _query_variants, _strip_detail
    from foms.services.common.address_converter import FOMSAddressConverter

    samples = [
        "오산역금강펜테리움1103-301",
        "경기 의왕시 시청로 42 108-1701",
        "동패동 2287-15",
    ]
    converter = FOMSAddressConverter.__new__(FOMSAddressConverter)
    for sample in samples:
        assert _strip_detail(sample) == strip_detail(sample)
        assert _query_variants(sample) == query_variants(sample)
        assert converter._strip_detail_for_geocoding(sample) == strip_detail(sample)


# --- NAVER-MATCH-01: 주소 매칭 키(match_key) ---------------------------------

_EQUIVALENT_TO_INCIDENT = [
    "서울특별시 성북구 화랑로48길 16 (석관동, 두산아파트) 110동 2403호",
    "서울시 성북구 화랑로48길 16 두산아파트 110동 2403호",
    "서울 성북구 화랑로48길 16, 두산아파트 110동 2403호",
    "성북구 화랑로48길 16, 두산아파트 110동 2403호",
    "성북구 화랑로48길 16",
]


def test_match_key_folds_notation_variants_to_one_key():
    """시/도 표기·괄호·쉼표·공백이 달라도 같은 집이면 같은 키가 나와야 한다."""
    from foms.services.common.address_query import match_key

    keys = {match_key(addr) for addr in _EQUIVALENT_TO_INCIDENT}
    assert keys == {"성북구화랑로48길16"}


def test_match_key_separates_different_buildings_and_districts():
    """음성 대조군 — 건물번호나 행정구역이 다르면 키가 갈려야 한다."""
    from foms.services.common.address_query import match_key

    base = match_key("서울특별시 성북구 화랑로48길 16 (석관동, 두산아파트) 110동 2403호")
    assert base != match_key("성북구 화랑로48길 18, 두산아파트 110동 2403호")
    assert base != match_key("성동구 화랑로48길 16, 두산아파트 110동 2403호")


def test_match_key_refuses_keys_too_coarse_to_identify_a_home():
    """행정구역 한 층만 남은 키는 사람을 특정하지 못한다 — 빈 문자열로 거절한다."""
    from foms.services.common.address_query import match_key

    for coarse in ("", "   ", "서울특별시", "서울 성북구", "성북구"):
        assert match_key(coarse) == ""


def test_strip_sido_keeps_words_that_merely_start_like_a_sido():
    """``서울시청로`` 처럼 낱말 한가운데를 자르면 안 된다."""
    from foms.services.common.address_query import strip_sido

    assert strip_sido("서울시청로 12") == "서울시청로 12"
    assert strip_sido("서울특별시 성북구 화랑로48길 16") == "성북구 화랑로48길 16"
    assert strip_sido("경기도수원시 팔달구 인계로 123") == "수원시 팔달구 인계로 123"
