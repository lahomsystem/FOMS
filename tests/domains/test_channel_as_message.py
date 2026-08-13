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


def _log(log_id: str, log_type: str, text: str, ts: str, round_no: int = 1, **extra) -> dict:
    entry = {
        "id": log_id, "type": log_type, "text": text, "ts": ts,
        "by": "고애희", "by_id": 3, "round": round_no,
    }
    entry.update(extra)
    return entry


def test_build_as_push_text_renders_construction_worker_block() -> None:
    """시공자는 고객정보와 AS 내용 사이 독립 블록 — 앞뒤 빈 줄 포함(사용자 확정 서식)."""
    order = _order(
        {
            "parties": {"customer": {"name": "이성민(용산)", "phone": "010-9040-5693"},
                        "orderer": {"name": "짓다인테리어"}},
            "site": {"address_full": "서울 용산구 백범로90길 74, 이안용산 103-502"},
            "schedule": {"construction": {"date": "2026-06-11"}},
            "shipment": {
                "as_content": "후드 교체 요청 - 유상AS\n후드값+시공비=140,000원 안내",
                "construction_workers": ["문정현"],
            },
        }
    )

    assert build_as_push_text(order).splitlines() == [
        "고객명 : 이성민(용산)",
        "발주사 : 짓다인테리어",
        "시공일 : 6월 11일",
        "주  소 : 서울 용산구 백범로90길 74, 이안용산 103-502",
        "연락처 : 010-9040-5693",
        "",
        "시공자 - 문정현",
        "",
        "내용 : 후드 교체 요청 - 유상AS",
        "후드값+시공비=140,000원 안내",
    ]


def test_build_as_push_text_joins_multiple_construction_workers() -> None:
    order = _order(
        {"shipment": {"as_content": "경첩 소음", "construction_workers": ["문정현", "김철수"]}},
        customer_name="홍길동",
    )
    assert "시공자 - 문정현, 김철수" in build_as_push_text(order)


def test_build_as_push_text_omits_worker_block_when_absent() -> None:
    """시공자가 없으면 줄도 빈 줄도 남기지 않는다 — 구주문 출력이 바뀌지 않아야 한다."""
    order = _order({"shipment": {"as_content": "문짝 처짐"}}, customer_name="홍길동")
    text = build_as_push_text(order)
    assert "시공자" not in text
    assert text.splitlines() == [
        "고객명 : 홍길동",
        "발주사 : 라홈",
        "시공일 : 상담",
        "",
        "내용 : 문짝 처짐",
    ]


def test_build_as_push_text_appends_current_round_records() -> None:
    """접수 이후 현재 회차 기록이 본문에 실린다(시간 오름차순, reception 중복 없음)."""
    order = _order(
        {
            "shipment": {
                "as_content": "후드 교체 요청",
                "as_log": [
                    _log("al_1", "reception", "후드 교체 요청", "2026-08-13T01:34:00"),
                    _log("al_2", "system", "AS 접수됨", "2026-08-13T01:35:00"),
                    _log("al_3", "plan", "후드 자재 발주 후 방문", "2026-08-13T02:00:00"),
                    _log("al_4", "call", "고객 오후만 가능", "2026-08-13T03:00:00"),
                ],
            }
        },
        customer_name="홍길동",
    )

    lines = build_as_push_text(order).splitlines()

    assert lines[-3:] == [
        "[1차 기록]",
        "- 8/13 방안: 후드 자재 발주 후 방문",
        "- 8/13 통화: 고객 오후만 가능",
    ]
    assert lines[-4] == ""  # 내용 블록과 빈 줄로 분리
    assert "AS 접수됨" not in "\n".join(lines)  # system 제외
    assert "\n".join(lines).count("후드 교체 요청") == 1  # reception 중복 없음


def test_build_as_push_text_round_block_excludes_other_rounds_and_deleted() -> None:
    """미결 판정 1건 = 2회차 개시. 1회차 기록·삭제 항목은 블록에 오지 않는다."""
    order = _order(
        {
            "shipment": {
                "as_content": "재방문 요청",
                "as_log": [
                    _log("al_1", "plan", "1회차 방안", "2026-08-10T01:00:00", 1),
                    _log("al_2", "verdict", "부품 부족", "2026-08-11T01:00:00", 1,
                         verdict="unresolved"),
                    _log("al_3", "memo", "지운 기록", "2026-08-12T01:00:00", 2, deleted=True),
                    _log("al_4", "material", "손잡이 재발주", "2026-08-12T02:00:00", 2),
                ],
            }
        },
        customer_name="홍길동",
    )

    text = build_as_push_text(order)

    assert "[2차 기록]" in text
    assert "- 8/12 자재: 손잡이 재발주" in text
    assert "1회차 방안" not in text
    assert "지운 기록" not in text
    assert "부품 부족" not in text  # verdict 는 발주처에 보낼 정보가 아니다


def test_build_as_push_text_round_block_keeps_newest_when_capped() -> None:
    """건수 상한 초과 시 잘리는 쪽은 **오래된** 기록이고, 생략 건수를 명시한다."""
    order = _order(
        {
            "shipment": {
                "as_content": "장기 AS",
                "as_log": [
                    _log(f"al_{i}", "memo", f"기록{i}", f"2026-08-13T{i:02d}:00:00")
                    for i in range(1, 14)
                ],
            }
        },
        customer_name="홍길동",
    )

    lines = build_as_push_text(order).splitlines()

    assert "- 외 3건" in lines
    assert lines[-1] == "- 8/13 메모: 기록13"
    assert not any("기록3:" in line or line.endswith("기록3") for line in lines)


def test_build_as_push_text_round_block_plain_texts_html() -> None:
    """as_log text 는 sanitize 통과 HTML — 채널톡은 plain text 라 태그가 남으면 안 된다."""
    order = _order(
        {
            "shipment": {
                "as_content": "AS",
                "as_log": [_log("al_1", "memo", "<p>상판 <b>교체</b></p>", "2026-08-13T01:00:00")],
            }
        },
        customer_name="홍길동",
    )

    text = build_as_push_text(order)

    assert "- 8/13 메모: 상판 교체" in text
    assert "<" not in text
