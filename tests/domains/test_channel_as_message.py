"""AS PUSH 본문 서버 조립기(channel_as_message) 계약.

본문은 ERP 주문수정 탭과 AS 대시보드 첨부 모달 두 화면이 공유하므로, 필드 출처와
표기 규칙을 여기서 고정한다.
"""

from __future__ import annotations

from types import SimpleNamespace

from foms.services.channel_as_message import build_as_push_text, format_schedule_date_korean


def _order(structured_data: dict, **flat) -> SimpleNamespace:
    base = {
        "customer_name": "",
        "phone": "",
        "address": "",
        "erp_construction_date": "",
        "structured_data": structured_data,
    }
    base.update(flat)
    return SimpleNamespace(**base)


def test_format_schedule_date_korean_handles_iso_multi_and_freeform() -> None:
    assert format_schedule_date_korean("2026-08-14") == "8월 14일"
    assert format_schedule_date_korean("2026-08-14,2026-09-02") == "8월 14일, 9월 2일"
    assert format_schedule_date_korean("미정") == "미정"
    assert format_schedule_date_korean("") == ""


def test_build_as_push_text_uses_structured_data_fields() -> None:
    order = _order(
        {
            "parties": {
                "customer": {"name": "옥은미", "phone": "010-5138-2120"},
                "orderer": {"name": "숨고"},
            },
            "site": {"address_full": "경남 창원시 마산합포구 산호북1길 15, 삼성타운아파트 102-1105"},
            "schedule": {"construction": {"date": "2026-08-14"}},
            "shipment": {"as_content": "문짝 처짐 재시공 요청"},
        }
    )

    text = build_as_push_text(order)

    assert text.splitlines() == [
        "고객명 : 옥은미",
        "발주사 : 숨고",
        "시공일 : 8월 14일",
        "주  소 : 경남 창원시 마산합포구 산호북1길 15, 삼성타운아파트 102-1105",
        "연락처 : 010-5138-2120",
        "",
        "내용 : 문짝 처짐 재시공 요청",
    ]


def test_build_as_push_text_falls_back_to_flat_columns() -> None:
    """structured_data 가 비어도 평면 컬럼으로 식별 정보를 채운다(구버전 주문)."""
    order = _order(
        {"shipment": {"as_content": "경첩 소음"}},
        customer_name="홍길동",
        phone="010-1111-2222",
        address="서울시 강남구",
        erp_construction_date="2026-09-01",
    )

    text = build_as_push_text(order)

    assert "고객명 : 홍길동" in text
    assert "발주사 : 라홈" in text  # 발주사 미지정 기본값
    assert "시공일 : 9월 1일" in text
    assert "주  소 : 서울시 강남구" in text
    assert "연락처 : 010-1111-2222" in text
    assert "내용 : 경첩 소음" in text


def test_build_as_push_text_returns_empty_without_as_content() -> None:
    """AS 접수 내용이 없으면 빈 문자열 — 라우트가 전송을 거부하는 신호."""
    order = _order({"parties": {"customer": {"name": "홍길동"}}}, customer_name="홍길동")
    assert build_as_push_text(order) == ""


def test_build_as_push_text_marks_missing_construction_date_as_consultation() -> None:
    order = _order({"shipment": {"as_content": "서랍 레일 교체"}}, customer_name="김철수")
    assert "시공일 : 상담" in build_as_push_text(order)
