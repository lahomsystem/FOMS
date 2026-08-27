"""AUDIT-GAP-01 후속: 원장 값 **절단 충돌**(화면에 ``A → A`` 로 보이는 행) 계약.

원장: ``docs/plans/2026-08-26-audit-gap-fill-ledger.md`` §T6 후속 별건 2.

배경: 원장 값은 두 번 줄어든다 — 쓰기 시점 120자 절단(``structured_diff._clip``)과 읽기 시점
60자 요약(``audit_message_display._LONG_TEXT_LIMIT``). 그래서 앞부분이 같은 긴 값은 실제로
바뀌었는데도 감사 화면에 ``A → A`` 로 나왔다. 읽는 사람은 그것을 버그로 여기고, **무엇이
바뀌었는지는 어디에도 없다.** 실측된 두 자리:

* ``options``(평면 컬럼) — ``direct`` 옵션의 **빈 JSON 스켈레톤만 162자**라
  ``misc``·``quote``·``option_detail`` 변경은 **항상** 같아 보였다.
* ``shipment.as_content`` — sanitize 된 HTML 이라 ``<div class="as-body"><p style="…">`` 만
  56자를 먹고 본문 중간의 태그가 남은 예산도 갉아먹는다.

여기서 고정하는 계약 4개:

1. **판정은 절단 전 원문으로** — 꼬리만 다른 긴 값도 변경으로 잡힌다(무기록 금지).
2. **표시값이 구별된다** — 원장 값에서 껍데기(HTML 태그·JSON 빈 칸)를 걷어내 같은 예산에
   내용을 싣고, 그래도 같아지면 :data:`CONTENT_MODIFIED_MARK` 로 구분한다.
3. **표식 리터럴은 한 벌** — 요약 축(site_extra·spec_rows)과 같은 상수를 쓴다.
4. **짧은 값 회귀 없음** — 절단이 일어나지 않는 값의 문장은 종전과 같다(표식이 붙지 않는다).
"""

from __future__ import annotations

import json

import pytest

from foms.services.audit_message_display import describe_change, format_value
from foms.services.orders.structured_diff import (
    CONTENT_MODIFIED_MARK,
    diff_structured,
    normalize_for_ledger,
    strip_markup,
)
from foms.web.orders.edit import _flat_change

#: sanitize 된 AS 본문의 실제 껍데기(`as_content_safety` 허용 태그 조합). 이것만 56자다.
_AS_HTML_HEAD = '<div class="as-body"><p style="margin:0">'
_AS_HTML_TAIL = "</p></div>"

#: 60자(읽기 요약 상한)를 넘기는 실제 AS 접수 문구.
_AS_BODY = (
    "현관 중문 상단 흠집 · 좌측 경첩 유격 · 손잡이 도장 벗겨짐 · 하단 몰딩 들뜸 · "
    "실리콘 재시공 필요 · 방문 전 기사 연락 요망 · 주차는 지하 2층"
)


def _as_html(tail: str) -> str:
    """꼬리만 다른 AS 본문 HTML 을 만든다.

    :param tail: 본문 끝에 붙일 문구.
    :return: sanitize 결과와 같은 모양의 HTML 문자열.
    """
    return f"{_AS_HTML_HEAD}{_AS_BODY} {tail}{_AS_HTML_TAIL}"


def _direct_options(**details: str) -> str:
    """``direct`` 옵션 컬럼 값(JSON 문자열)을 만든다 — 빈 칸 포함 실제 저장 모양.

    :param details: 채울 칸(나머지는 빈 문자열).
    :return: ``Order.options`` 에 저장되는 JSON 문자열.
    """
    keys = (
        "product_name", "spec", "internal", "color",
        "option_detail", "handle", "misc", "quote",
    )
    payload = {
        "option_type": "direct",
        "details": {key: details.get(key, "") for key in keys},
    }
    return json.dumps(payload, ensure_ascii=False)


# --------------------------------------------------------------------------
# 0. 문제 재현 조건 — 이 전제가 깨지면 아래 테스트가 아무것도 지키지 않는다
# --------------------------------------------------------------------------
def test_the_collision_preconditions_are_real() -> None:
    """두 값 모두 절단 상한(120자)을 넘고, 예산을 **껍데기**에 쓰고 있었다."""
    assert len(_direct_options()) > 120, "빈 옵션 스켈레톤이 이미 상한을 넘어야 한다"

    raw = _as_html("기사 A")
    assert len(raw) > 120
    # 종전 규칙(HTML 원문을 120자에서 절단)이 남기던 본문 < 태그를 먼저 벗겼을 때 남는 본문.
    assert len(strip_markup(raw[:120])) < len(strip_markup(raw)[:120])


# --------------------------------------------------------------------------
# 1. shipment.as_content — 꼬리만 다른 긴 HTML
# --------------------------------------------------------------------------
def test_as_content_tail_edit_is_recorded() -> None:
    """꼬리만 고친 긴 HTML 도 **변경으로 잡힌다**(판정은 절단 전 원문)."""
    result = diff_structured(
        {"shipment": {"as_content": _as_html("기사 김OO 방문 예정")}},
        {"shipment": {"as_content": _as_html("기사 박OO 방문 예정")}},
    )

    assert [c["path"] for c in result.changes] == ["shipment.as_content"]


def test_as_content_ledger_value_carries_body_not_markup() -> None:
    """원장 값은 태그가 아니라 **본문**을 싣는다 — 같은 120자를 무엇에 쓰느냐의 문제다."""
    change = diff_structured(
        {"shipment": {"as_content": _as_html("기사 김OO")}},
        {"shipment": {"as_content": _as_html("기사 박OO")}},
    ).changes[0]

    assert "<" not in str(change["before"])
    assert "class=" not in str(change["before"])
    assert str(change["before"]).startswith("현관 중문 상단 흠집")


def test_as_content_before_and_after_are_distinguishable() -> None:
    """화면 문장에서 before 와 after 가 **서로 구별된다**(``A → A`` 금지)."""
    change = diff_structured(
        {"shipment": {"as_content": _as_html("기사 김OO 방문 예정")}},
        {"shipment": {"as_content": _as_html("기사 박OO 방문 예정")}},
    ).changes[0]

    line = describe_change(change)
    before_text, _, after_text = line.partition(" → ")
    assert before_text != after_text, line
    assert CONTENT_MODIFIED_MARK in after_text, line


def test_as_content_markup_only_edit_is_still_a_change() -> None:
    """태그만 바뀐 저장도 기록된다 — 표시값을 줄였다고 판정까지 줄이지 않는다."""
    result = diff_structured(
        {"shipment": {"as_content": "<p>문 흠집</p>"}},
        {"shipment": {"as_content": "<p><b>문 흠집</b></p>"}},
    )

    assert [c["path"] for c in result.changes] == ["shipment.as_content"]
    assert CONTENT_MODIFIED_MARK in describe_change(result.changes[0])


def test_as_content_markup_only_body_is_not_faked_into_empty() -> None:
    """태그뿐인 본문을 빈값으로 둔갑시키지 않는다(없는 '지움' 을 만들지 않는다)."""
    change = diff_structured(
        {"shipment": {"as_content": "<p>문 흠집</p>"}},
        {"shipment": {"as_content": "<br>"}},
    ).changes[0]

    assert change["after"] == "<br>"
    assert change["op"] == "set"


# --------------------------------------------------------------------------
# 2. options — 평면 컬럼(emit 은 edit.py, 표시 규칙만 여기 소관)
# --------------------------------------------------------------------------
def test_options_tail_field_edit_is_recorded() -> None:
    """스켈레톤 뒤쪽 칸(``misc``)만 고쳐도 변경으로 잡힌다."""
    row = _flat_change("options", _direct_options(misc="AAA"), _direct_options(misc="BBB"))

    assert row is not None
    assert row["path"] == "options"
    assert row["op"] == "set"


def test_options_ledger_value_drops_the_empty_skeleton() -> None:
    """원장 값은 빈 칸을 걷어낸 JSON 이다 — 162자 껍데기가 예산을 먹지 않는다."""
    value = normalize_for_ledger(_direct_options(misc="AAA"), "options")

    assert value is not None
    assert "AAA" in value
    assert '"quote"' not in value, "빈 칸은 걷어낸다"
    assert not value.endswith("…"), f"절단되지 않아야 한다: {value}"


def test_options_before_and_after_are_distinguishable() -> None:
    """뒤쪽 칸 변경이 화면 문장에서 구별된다 — 종전에는 두 값이 같은 120자였다."""
    row = _flat_change("options", _direct_options(misc="AAA"), _direct_options(misc="BBB"))
    line = describe_change(row)
    before_text, _, after_text = line.partition(" → ")

    assert before_text != after_text, line
    assert "AAA" in before_text and "BBB" in after_text, line


def test_options_beyond_the_budget_falls_back_to_the_mark() -> None:
    """빈 칸을 걷어내고도 상한을 넘는 긴 옵션은 **표식**으로 구별한다.

    직렬화는 키 정렬이라 ``quote`` 는 맨 뒤다 — 앞 칸(``color``)이 길면 뒤 칸 변경은 절단
    너머로 밀린다. 이때가 표식이 유일한 단서인 자리다.
    """
    filler = "고객 요청 사항 상세 " * 12
    row = _flat_change(
        "options",
        _direct_options(color=filler, quote="AAA"),
        _direct_options(color=filler, quote="BBB"),
    )
    line = describe_change(row)

    assert row["before"] == row["after"], "이 경우는 저장값 자체가 같아진다(전제)"
    assert CONTENT_MODIFIED_MARK in line.partition(" → ")[2], line


def test_options_non_json_value_is_left_alone() -> None:
    """JSON 이 아닌 옛 자유 텍스트 옵션은 손대지 않는다(무성 변형 금지)."""
    assert normalize_for_ledger("상판 추가 · 색상 변경", "options") == "상판 추가 · 색상 변경"


# --------------------------------------------------------------------------
# 3. 표식 리터럴은 한 벌 — 요약 축과 같은 상수
# --------------------------------------------------------------------------
def test_summary_axis_still_marks_content_only_edits() -> None:
    """현장 특이사항 요약(건수 동일 + 내용 변경)은 종전대로 쓰기 시점에 표식을 단다."""
    change = diff_structured(
        {"shipment": {"site_extra": [{"text": "엘리베이터 없음", "color": ""}]}},
        {"shipment": {"site_extra": [{"text": "엘리베이터 점검 중", "color": ""}]}},
    ).changes[0]

    assert change["before"] == "1건"
    assert change["after"] == f"1건{CONTENT_MODIFIED_MARK}"
    # 쓰기 시점 표식이 있으면 before != after 이므로 읽기 시점 표식이 겹쳐 붙지 않는다.
    assert describe_change(change).count(CONTENT_MODIFIED_MARK) == 1


def test_spec_rows_same_row_count_is_marked_too() -> None:
    """규격표도 행 수가 같으면 ``2행 → 2행`` 이었다 — 같은 표식으로 구분한다."""
    old_item = {"uid": "u1", "spec_rows": [["가", "1"], ["나", "2"]]}
    new_item = {"uid": "u1", "spec_rows": [["가", "1"], ["나", "9"]]}
    change = diff_structured({"items": [old_item]}, {"items": [new_item]}).changes[0]

    assert change["path"] == "items.0.spec_rows"
    assert CONTENT_MODIFIED_MARK in describe_change(change)


# --------------------------------------------------------------------------
# 4. 회귀 — 짧은 값은 종전과 똑같이 읽힌다
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"path": "payment.balance_note", "before": "설치 후 현금", "after": "계좌 이체",
          "op": "set"}, "잔금 비고 설치 후 현금 → 계좌 이체"),
        ({"path": "schedule.measurement.date", "before": "2026-08-12", "after": "2026-08-14",
          "op": "set"}, "실측일 2026-08-12 → 2026-08-14"),
        ({"path": "payment.deposit", "before": None, "after": "100000",
          "op": "add"}, "예약금 입력 (없음) → 100,000"),
        ({"path": "flags.urgent_reason", "before": "고객 요청", "after": None,
          "op": "clear"}, "긴급 사유 고객 요청 → (지움)"),
    ],
)
def test_short_values_read_exactly_as_before(change: dict, expected: str) -> None:
    """절단이 없는 값에는 표식이 붙지 않는다."""
    assert describe_change(change) == expected


def test_empty_to_empty_row_is_not_marked_as_content_edit() -> None:
    """빈값 → 빈값 행은 "내용 수정" 이 아니다(표기만 다를 뿐 같은 상태다)."""
    line = describe_change({"path": "notes", "before": None, "after": None, "op": "clear"})

    assert line == "비고 (없음) → (지움)"
    assert CONTENT_MODIFIED_MARK not in line


def test_short_as_content_is_summarized_as_before() -> None:
    """짧은 AS 본문 표기는 종전과 같다(태그 제거 후 본문)."""
    change = diff_structured(
        {"shipment": {"as_content": "<div>문 흠집</div>"}},
        {"shipment": {"as_content": "<div>상판 교체</div>"}},
    ).changes[0]

    assert describe_change(change) == "AS 내용 문 흠집 → 상판 교체"
    assert format_value("as_content", change["after"]) == "상판 교체"
