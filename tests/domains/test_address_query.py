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


def test_beon_gil_road_is_not_truncated() -> None:
    """``NNN번길`` 은 앞 도로와 **다른 도로**다 — 건물번호에서 자르면 안 된다.

    2026-09-01 조사: ``판교로 256번길 25`` 가 ``판교로 256`` 으로 잘렸다. 잘린 값도
    카카오에서 좌표가 나오므로 실패가 아니라 **엉뚱한 좌표로 성공**한다(핀이 수백 m~수 km
    어긋난 채 정상으로 보인다 — 실패보다 나쁘다).
    """
    assert strip_detail("서울 강남구 강남대로 123번길 45") == "서울 강남구 강남대로 123번길 45"
    assert (strip_detail("경기 성남시 분당구 판교로 256번길 25 (삼평동)")
            == "경기 성남시 분당구 판교로 256번길 25")
    assert (strip_detail("인천 서구 청라한내로 88번길 12-3 202동 1503호")
            == "인천 서구 청라한내로 88번길 12-3")


def test_beon_gil_guard_does_not_split_building_number() -> None:
    r"""음성 대조군: 번길 방어가 건물번호 자릿수를 갉아먹으면 안 된다.

    부정 전방탐색만 두면 백트래킹이 ``123`` 을 ``12`` 로 줄여 전방탐색을 우회한다 —
    원래 결함보다 나쁜 절단이다. 숫자 경계(``(?!\d)``)가 함께 있어야 한다.
    """
    for sample in ("서울 강남구 강남대로 123번길 45", "경기 성남시 분당구 판교로 256번길 25"):
        assert strip_detail(sample) == sample
        assert sample in query_variants(sample)


def test_plain_road_addresses_still_truncate() -> None:
    """음성 대조군: ``번길`` 이 없는 도로명은 종전대로 건물번호까지만 남는다."""
    assert strip_detail("서울 강남구 테헤란로 152 5층") == "서울 강남구 테헤란로 152"
    assert strip_detail("서울 서초구 서초대로 396 강남빌딩 5층") == "서울 서초구 서초대로 396"
    assert (strip_detail("경기 고양시 일산서구 강선로 188 (일산동, 후곡마을11단지아파트) 1105동 1406호")
            == "경기 고양시 일산서구 강선로 188")


def test_attached_road_number_gil_is_unchanged() -> None:
    """음성 대조군: ``통일로68길 4`` 처럼 붙여쓴 길 표기는 종전 결과를 유지한다."""
    assert strip_detail("서울시 은평구 통일로68길 4 101동 202호") == "서울시 은평구 통일로68길 4"


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
