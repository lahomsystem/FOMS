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
