"""구 이름 정규화 계약 (``FOMSAdvancedAddressProcessor._normalize_district``).

2026-09-01 조사: ``common_mistakes`` 의 ``'강남'->'강남구'`` 가 **부분 문자열 전역 치환**
이라 ``서울특별시 서초구 서초대로 396 강남빌딩 5층`` 의 건물명이 ``강남구빌딩`` 이 되고,
:meth:`extract_address_components` 가 ``district='강남구'`` 로 뒤집혔다. 그 상태로 변환기
6단계 ``simplified`` 폴백이 돌면 "서울특별시 강남구" 좌표를 **성공으로** 반환한다 —
서초구 주소에 강남구 핀이 꽂힌다.

치환 자체는 살아 있어야 한다(``서울 강남 역삼동`` -> ``강남구``). 그래서 이 스위트는
"치환이 죽었는지" 보는 음성 대조군을 반드시 함께 돌린다.
"""
from __future__ import annotations

import pytest

from foms.services.common.address_ai_ops_loader import FOMSAdvancedAddressProcessor


@pytest.fixture(scope="module")
def processor() -> FOMSAdvancedAddressProcessor:
    return FOMSAdvancedAddressProcessor()


def test_building_name_is_not_turned_into_a_district(processor) -> None:
    """건물명 안의 '강남'은 구 이름이 아니다 — 치환하지 않는다."""
    processed = processor.process_address("서울특별시 서초구 서초대로 396 강남빌딩 5층")
    assert "강남구빌딩" not in processed
    assert "강남빌딩" in processed


def test_components_keep_the_real_district(processor) -> None:
    """구 추출이 뒤집히지 않는다(이 값이 simplified 폴백 좌표를 정한다)."""
    components = processor.extract_address_components("서울특별시 서초구 서초대로 396 강남빌딩 5층")
    assert components["district"] == "서초구"


def test_bare_district_name_is_still_completed(processor) -> None:
    """음성 대조군: 낱말로 선 '강남'은 종전대로 '강남구'로 보완된다."""
    processed = processor.process_address("서울 강남 역삼동 123-45")
    assert "강남구" in processed
    assert processor.extract_address_components("서울 강남 역삼동 123-45")["district"] == "강남구"


@pytest.mark.parametrize(
    "address, expected_district",
    [
        ("서울 송파 올림픽로 300", "송파구"),          # 보완 살아있음
        ("서울특별시 강남구 테헤란로 152", "강남구"),   # 이미 완전 — 무변경
        ("서울특별시 서초구 서초대로 396", "서초구"),   # 다른 구 오염 없음
    ],
)
def test_district_completion_matrix(processor, address, expected_district) -> None:
    """양성(보완)·음성(무변경) 양쪽을 한 표로 고정한다."""
    assert processor.extract_address_components(address)["district"] == expected_district


def test_no_double_suffix(processor) -> None:
    """음성 대조군: 이미 '구'가 붙은 이름에 다시 붙이지 않는다('강남구구')."""
    processed = processor.process_address("서울특별시 강남구 테헤란로 152")
    assert "강남구구" not in processed


# --------------------------------------------------------------------------- #
# 동 추출 — 구 이름에서 동을 만들어 내지 않는다 (GEO-COARSE-01)
# --------------------------------------------------------------------------- #
def test_dong_is_not_taken_from_the_district_name(processor) -> None:
    """`성동구` 의 `성동` 은 동 이름이 아니다.

    운영 #2418: 이 오추출이 6단계 폴백에 `서울특별시 성동구 성동` 을 물어보게 만들어,
    진짜 위치(금호4가동)에서 **2,214m** 떨어진 좌표가 success 로 저장됐다(2026-09-02 실측).
    """
    components = processor.extract_address_components(
        "서울시 성동구 금호4가동 1546-4, 힐스테이트서울숲리버 112동 1101호")
    assert components["district"] == "성동구"
    assert components["dong"] == "금호4가동"


def test_apartment_building_number_is_not_a_dong(processor) -> None:
    """`112동` 은 아파트 동 번호지 동 이름이 아니다."""
    components = processor.extract_address_components("서울 강남구 테헤란로 152 112동 1101호")
    assert components["dong"] is None


@pytest.mark.parametrize(
    "address, expected_dong",
    [
        ("서울 관악구 성현동, 관악센트씨엘 101동 405호", "성현동"),      # 정상 추출(양성)
        ("경기도 오산시 궐동 432-4 세교파라곤 412동 1201호", "궐동"),    # 정상 추출(양성)
        ("부산 해운대구 우동 1407 마린시티 101동 202호", "우동"),        # 두 글자 동(양성)
        ("서울 강남구 테헤란로 152 5층", None),                          # 동 없음(음성)
    ],
)
def test_dong_extraction_matrix(processor, address, expected_dong) -> None:
    """양성·음성을 한 표로 고정한다(동을 아예 못 뽑는 퇴화 구현 차단)."""
    assert processor.extract_address_components(address)["dong"] == expected_dong
