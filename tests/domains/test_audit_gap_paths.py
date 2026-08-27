"""AUDIT-GAP-01 T2: 화이트리스트 확대 · 요약 축 · 라벨/표기 등재 계약.

원장: ``docs/plans/2026-08-26-audit-gap-fill-ledger.md``.

배경: ``order_field_changes`` 원장은 ``structured_diff.SCALAR_PATHS`` 화이트리스트만 본다.
운영 실측(2026-08-26)에서 저장 2건 중 1건 이상이 무기록이었고, 구멍의 한 축이 "값이
화이트리스트에 없다"였다.

여기서 고정하는 계약 5개:

1. **새 감사 경로**(``payment.balance_note``·``shipment.as_content``)가 등재되고 한글 라벨을 갖는다.
2. **라벨 표**(원장 §라벨·표기 표) 전 행이 :data:`PATH_LABELS` 에 있다 — 다른 task 가 emit 할
   평면 컬럼까지 지금 등재한다(라벨이 없으면 감사 화면에 영문 컬럼명이 그대로 뜬다).
3. **체크박스 값 표기** — 체크리스트류는 ``예/아니오`` 가 아니라 ``완료/해제`` 로 읽힌다.
4. **현장 특이사항 요약** — 건수가 같아도 내용이 바뀌면 변경으로 잡히고, 원장 값은 절단된
   JSON 원문이 아니다.
5. **되돌리기 화이트리스트 불변** — bool·메모류는 복원 대상이 아니다.
"""

from __future__ import annotations

import json

import pytest

from foms.services.audit_message_display import (
    FIELD_LABELS,
    PATH_LABELS,
    _PATH_VALUE_FIELD,
    describe_change,
    describe_field_change,
    field_label,
    format_value,
    path_label,
)
from foms.services.orders.status_constants import CABINET_STATUS
from foms.services.orders.field_restore import RESTORABLE_PATHS
from foms.services.orders.structured_diff import (
    SCALAR_PATHS,
    SITE_EXTRA_PATH,
    diff_structured,
)

#: 원장 "라벨·표기 표" 전문(정본). 표가 바뀌면 여기도 함께 바뀐다.
_LEDGER_LABELS: dict[str, str] = {
    "is_self_measurement": "자가실측",
    "order_notes": "주문 비고",
    "received_date": "접수일",
    "received_time": "접수시간",
    "payment.balance_note": "잔금 비고",
    "shipment.as_content": "AS 내용",
    "shipment.site_extra": "현장 특이사항",
    "is_cabinet": "수납장",
    "cabinet_status": "수납장 상태",
    "shipping_fee": "배송비",
    "payment_amount": "결제금액",
    "completion_date": "설치완료일",
    "as_received_date": "AS 접수일",
    "as_completed_date": "AS 완료일",
    "shipping_scheduled_date": "상차 예정일",
    "options": "옵션 상세",
    "status": "상태",
    "regional_sales_order_upload": "영업발주 업로드",
    "regional_blueprint_sent": "도면 발송",
    "regional_order_upload": "발주 업로드",
    "regional_cargo_sent": "화물 발송",
    "regional_construction_info_sent": "시공정보 발송",
    "measurement_completed": "실측완료",
    # T4b 후속(2026-08-26): 지방 메모 변경도 원장에 실린다(``regional.py`` path=regional_memo).
    "regional_memo": "지방 메모",
}

#: 체크박스로 입력되는 경로 — 값이 ``완료/해제`` 로 읽혀야 한다.
_CHECKBOX_PATHS = (
    "is_self_measurement",
    "is_cabinet",
    "measurement_completed",
    "regional_sales_order_upload",
    "regional_blueprint_sent",
    "regional_order_upload",
    "regional_cargo_sent",
    "regional_construction_info_sent",
)


def _sd_site_extra(*entries: dict[str, str]) -> dict[str, object]:
    """``shipment.site_extra`` 만 담은 ``structured_data`` 를 만든다."""
    return {"shipment": {"site_extra": list(entries)}}


# --------------------------------------------------------------------------
# 1. 화이트리스트 확대
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["payment.balance_note", "shipment.as_content"])
def test_new_scalar_paths_are_audited_and_labelled(path: str) -> None:
    """잔금 비고·AS 내용 변경이 원장에 남고 한글 라벨을 갖는다."""
    assert path in SCALAR_PATHS
    assert PATH_LABELS[path]


def test_balance_note_change_is_recorded() -> None:
    """잔금 비고를 고치면 before → after 가 남는다(2026-08-26 이전에는 흔적이 없었다)."""
    result = diff_structured(
        {"payment": {"balance_note": "설치 후 현금"}},
        {"payment": {"balance_note": "계좌 이체"}},
    )

    assert [(c["path"], c["before"], c["after"], c["op"]) for c in result.changes] == [
        ("payment.balance_note", "설치 후 현금", "계좌 이체", "set"),
    ]


def test_as_content_overwrite_is_recorded() -> None:
    """AS 본문 덮어쓰기가 남는다 — as_log 는 append-only 라 덮어쓰기를 잡지 못한다."""
    result = diff_structured(
        {"shipment": {"as_content": "<div>문 흠집</div>"}},
        {"shipment": {"as_content": "<div>상판 교체</div>"}},
    )

    paths = [c["path"] for c in result.changes]
    assert paths == ["shipment.as_content"]


def test_as_visit_availability_is_audited_after_the_preservation_fix() -> None:
    """``schedule.as_visit.availability`` 는 **보존 결함을 고친 뒤** 등재됐다.

    처음에는 범위 밖이었다 — 폼 저장마다 ``as_visit`` 이 통째로 소실되던 별개 결함이 있어,
    그 상태로 등재하면 저장 1회에 허위 '지움' 행이 쌓이기 때문이다. 2026-08-26 에
    ``_preserve_operational_structured_state`` 의 deep-merge 목록에 ``schedule`` 을 넣어
    보존을 먼저 고쳤고(``tests/domains/test_audit_gap_as_visit.py`` 가 고정), 그 다음 등재했다.

    순서가 뒤집히면 원장이 가짜 '지움' 으로 오염된다 — 그래서 두 계약을 함께 둔다.
    """
    assert "schedule.as_visit.availability" in SCALAR_PATHS
    assert path_label("schedule.as_visit.availability") == "AS 방문 가능시간"
    # 가능시간 dict 가 화면에 JSON 원문으로 뜨지 않는다(값 표기 위임이 걸려 있다).
    rendered = format_value("as_visit_availability", {"days": "weekday", "time": "am"})
    assert "{" not in rendered and rendered.strip() != ""


# --------------------------------------------------------------------------
# 2. 라벨 등재
# --------------------------------------------------------------------------
@pytest.mark.parametrize(("path", "label"), sorted(_LEDGER_LABELS.items()))
def test_path_label_matches_the_ledger_table(path: str, label: str) -> None:
    """원장 라벨 표 전 행이 그대로 화면 라벨이 된다."""
    assert path_label(path) == label


@pytest.mark.parametrize(("field", "label"), [
    ("shipping_fee", "배송비"),
    ("cabinet_status", "수납장 상태"),
    ("as_received_date", "AS 접수일"),
])
def test_flat_columns_have_message_labels_too(field: str, label: str) -> None:
    """``security_logs.message`` 를 쓰는 경로도 한글을 쓴다.

    ``FIELD_LABELS`` 는 :func:`describe_field_change` 가 쓰는 평면 컬럼 사전이다. 여기 없으면
    사람이 읽는 문장 한복판에 영문 컬럼명이 그대로 박힌다.
    """
    assert field_label(field) == label
    assert FIELD_LABELS[field] == label
    assert label in describe_field_change(order_id=1, field=field, after="X")


def test_regional_memo_label_differs_from_the_message_dictionary_on_purpose() -> None:
    """원장 행에는 주문 접두가 없어 "메모"만으로는 어느 메모인지 알 수 없다."""
    assert path_label("regional_memo") == "지방 메모"
    # 문장 쪽은 ``지방 주문 #N (…) — 메모: …`` 로 접두가 이미 "지방"을 말한다.
    assert FIELD_LABELS["regional_memo"] == "메모"


def test_order_notes_is_not_the_same_label_as_structured_notes() -> None:
    """평면 ``Order.notes`` 와 sd ``notes`` 객체는 다른 값이라 라벨을 나눈다.

    같은 라벨이면 감사 화면에 뜻이 다른 "비고" 두 줄이 나란히 뜬다.
    """
    assert path_label("notes") == "비고"
    assert path_label("order_notes") == "주문 비고"
    assert path_label("order_notes") != path_label("notes")


# --------------------------------------------------------------------------
# 3. 값 표기(체크박스·상태 코드)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", _CHECKBOX_PATHS)
def test_checkbox_paths_read_as_business_state(path: str) -> None:
    """체크박스류는 '예/아니오' 가 아니라 '완료/해제' 로 읽힌다."""
    value_field = _PATH_VALUE_FIELD[path]
    assert format_value(value_field, True) == "완료"
    assert format_value(value_field, "False") == "해제"


@pytest.mark.parametrize("path", _CHECKBOX_PATHS)
def test_checkbox_change_row_reads_as_business_state(path: str) -> None:
    """원장 행 한 줄로 폈을 때도 같은 말이 나온다(쓰기 경로와 화면이 같은 규격)."""
    text = describe_change({"path": path, "before": "False", "after": "True", "op": "set"})
    assert text == f"{PATH_LABELS[path]} 해제 → 완료"


def test_cabinet_status_reads_as_korean_not_a_code() -> None:
    """수납장 상태는 ``SHIPPED`` 가 아니라 ``발송`` 으로 읽힌다."""
    assert _PATH_VALUE_FIELD["cabinet_status"] == "cabinet_status"
    assert format_value("cabinet_status", "SHIPPED") == "발송"
    assert describe_change(
        {"path": "cabinet_status", "before": "RECEIVED", "after": "IN_PRODUCTION", "op": "set"}
    ) == "수납장 상태 접수 → 제작중"


def test_cabinet_status_dictionary_is_not_copied() -> None:
    """한글 사전은 업무 로직의 것을 재사용한다 — 베껴 쓰면 코드가 늘 때 화면만 낡는다."""
    for code, korean in CABINET_STATUS.items():
        assert format_value("cabinet_status", code) == korean


def test_unknown_cabinet_status_code_is_not_hidden() -> None:
    """사전에 없는 코드는 원문 그대로 낸다(감사 화면은 모르는 값을 감추지 않는다)."""
    assert format_value("cabinet_status", "BRAND_NEW_CODE") == "BRAND_NEW_CODE"


def test_flat_status_path_reads_as_korean_stage() -> None:
    """평면 ``status`` 컬럼도 단계 코드가 아니라 한글 단계명으로 읽힌다."""
    assert _PATH_VALUE_FIELD["status"] == "status"
    assert describe_change(
        {"path": "status", "before": "RECEIVED", "after": "MEASURE", "op": "set"}
    ) == "상태 접수 → 실측"


# --------------------------------------------------------------------------
# 4. 현장 특이사항 요약
# --------------------------------------------------------------------------
def test_site_extra_count_change_is_summarized_not_dumped() -> None:
    """건수 변화는 ``2건 → 3건`` 으로 남는다 — JSON 원문이 아니다."""
    result = diff_structured(
        _sd_site_extra({"text": "잠금장치", "color": "red"},
                       {"text": "오전만 방문", "color": "gray"}),
        _sd_site_extra({"text": "잠금장치", "color": "red"},
                       {"text": "오전만 방문", "color": "gray"},
                       {"text": "엘리베이터 없음", "color": "gray"}),
    )

    assert len(result.changes) == 1
    change = result.changes[0]
    assert change["path"] == SITE_EXTRA_PATH
    assert (change["before"], change["after"]) == ("2건", "3건")
    assert describe_change(change) == "현장 특이사항 2건 → 3건"


def test_site_extra_content_edit_is_caught_even_when_count_is_equal() -> None:
    """건수가 같아도 문구가 바뀌면 변경으로 잡는다 — 건수만 비교하면 통째로 놓친다."""
    result = diff_structured(
        _sd_site_extra({"text": "엘리베이터 없음", "color": "gray"}),
        _sd_site_extra({"text": "엘리베이터 있음", "color": "gray"}),
    )

    assert len(result.changes) == 1
    change = result.changes[0]
    assert change["path"] == SITE_EXTRA_PATH
    # 건수가 같으니 표시값만으로는 구분이 안 된다 — 표식으로 "무엇이 달라졌는지"를 밝힌다.
    assert change["before"] != change["after"]
    assert "1건" in change["before"] and "1건" in change["after"]


def test_site_extra_color_only_edit_is_caught() -> None:
    """색(강조)만 바뀌어도 변경이다 — 현장 특이사항의 색은 우선순위 표시다."""
    result = diff_structured(
        _sd_site_extra({"text": "잠금장치", "color": "gray"}),
        _sd_site_extra({"text": "잠금장치", "color": "red"}),
    )

    assert [c["path"] for c in result.changes] == [SITE_EXTRA_PATH]


def test_site_extra_values_are_never_clipped_json() -> None:
    """긴 본문이어도 원장 값에 JSON 조각이 실리지 않는다(절단되면 before==after 로 보인다)."""
    long_text = "가" * 500
    result = diff_structured(
        _sd_site_extra({"text": long_text, "color": "gray"}),
        _sd_site_extra({"text": long_text, "color": "gray"},
                       {"text": long_text + "나", "color": "gray"}),
    )

    change = result.changes[0]
    for value in (change["before"], change["after"]):
        assert "{" not in value and "…" not in value
        assert len(value) <= 8


def test_site_extra_unchanged_content_is_not_a_change() -> None:
    """같은 내용을 다시 저장하면 아무것도 남지 않는다(저장 버튼 소음 금지)."""
    same = _sd_site_extra({"text": "잠금장치", "color": "red"})
    assert diff_structured(same, json.loads(json.dumps(same))).changes == []


def test_site_extra_empty_entries_are_not_a_change() -> None:
    """빈 칸 항목이 늘거나 줄어도 변경이 아니다 — 폼이 빈 줄을 저장한 흔적이다."""
    result = diff_structured(
        _sd_site_extra({"text": "잠금장치", "color": "red"}),
        _sd_site_extra({"text": "잠금장치", "color": "red"}, {"text": "  ", "color": "gray"}),
    )

    assert result.changes == []


def test_site_extra_is_not_in_the_scalar_whitelist() -> None:
    """요약 축이라 스칼라 루프에 넣지 않는다 — 넣으면 같은 경로가 두 번 기록된다."""
    assert SITE_EXTRA_PATH not in SCALAR_PATHS


# --------------------------------------------------------------------------
# 5. 되돌리기 화이트리스트 불변
# --------------------------------------------------------------------------
def test_new_paths_are_not_restorable() -> None:
    """bool·메모·요약 축은 값 되쓰기 복원 대상이 아니다(원장 §범위 밖)."""
    for path in ("payment.balance_note", "shipment.as_content", SITE_EXTRA_PATH):
        assert path not in RESTORABLE_PATHS
    for path in _LEDGER_LABELS:
        assert path not in RESTORABLE_PATHS
