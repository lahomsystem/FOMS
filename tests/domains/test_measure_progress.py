"""실측 전/후 판정 계약 (2026-09-07) — foms/services/orders/measure_progress.py.

취소·반품이 들어왔을 때 "실측을 하고 취소인지"를 화면·알림이 같은 낱말로 말하려면
판정이 한 곳에만 있어야 한다. 이 계약이 그 한 곳을 고정한다.

DB 를 쓰지 않는다 — ``SimpleNamespace`` 스텁으로 실측일 리더
(``extract_all_measurement_dates``)의 입력 모양만 맞춰 돌린다.
"""

from __future__ import annotations

import ast
import datetime
from pathlib import Path
from types import SimpleNamespace

from foms.services.orders import measure_progress as mp
from foms.services.orders.measure_progress import (
    MEASURE_AFTER,
    MEASURE_BEFORE,
    MEASURE_NONE,
    judge_measure_progress,
)

TODAY = datetime.date(2026, 9, 7)


def _order(
    *,
    dates: list[str] | None = None,
    status: str = "RECEIVED",
    workflow_stage: str | None = None,
    measurement_completed: bool = False,
    measurement_date: str | None = None,
    is_erp_order: bool = True,
) -> SimpleNamespace:
    """ERP 주문 스텁. ``dates`` 는 structured schedule 의 실측일(복수 가능)."""
    structured_data: dict = {}
    if dates:
        structured_data["schedule"] = {"measurement": {"date": ",".join(dates)}}
    if workflow_stage is not None:
        structured_data["workflow"] = {"stage": workflow_stage}
    return SimpleNamespace(
        id=5164,
        is_erp_order=is_erp_order,
        structured_data=structured_data,
        schedule_dates=None,
        measurement_date=measurement_date,
        measurement_completed=measurement_completed,
        status=status,
    )


def test_past_measurement_date_is_after():
    """실측일이 지났으면 실측 후 — 화면은 MM-DD, 알림은 ISO."""
    got = judge_measure_progress(_order(dates=["2026-09-02"]), today=TODAY)
    assert got.code == MEASURE_AFTER
    assert got.label == "실측 후"
    assert got.basis == "schedule"
    assert got.basis_text == "실측 일정"
    assert got.date == "2026-09-02"
    assert got.text == "실측 후 · 09-02"
    assert got.notice == "실측을 마친 뒤입니다(실측 2026-09-02)."


def test_today_counts_as_after():
    """오늘이 실측일이면 이미 나간 것으로 본다(오늘 이하)."""
    got = judge_measure_progress(_order(dates=["2026-09-07"]), today=TODAY)
    assert got.code == MEASURE_AFTER
    assert got.date == "2026-09-07"


def test_future_measurement_date_is_before():
    """실측일이 미래면 아직 실측 전이다."""
    got = judge_measure_progress(_order(dates=["2026-09-12"]), today=TODAY)
    assert got.code == MEASURE_BEFORE
    assert got.label == "실측 전"
    assert got.basis == "schedule"
    assert got.date == "2026-09-12"
    assert got.text == "실측 전 · 09-12 예정"
    assert got.notice == "아직 실측 전입니다(실측 예정 2026-09-12)."


def test_no_measurement_date_is_none_and_says_so():
    """근거가 없으면 모른다고 말한다 — 날짜를 지어내지 않는다."""
    got = judge_measure_progress(_order(), today=TODAY)
    assert got.code == MEASURE_NONE
    assert got.label == "실측일 없음"
    assert got.date == ""
    assert got.basis == "unknown"
    assert got.basis_text == ""
    assert got.text == "실측일 없음"
    assert not any(ch.isdigit() for ch in got.text)
    assert got.notice == "실측 일정이 없어 실측 전인지 후인지 모릅니다."


def test_measurement_completed_without_date_is_after():
    """사람이 찍은 실측완료 표시는 날짜가 없어도 실측 후다."""
    got = judge_measure_progress(_order(measurement_completed=True), today=TODAY)
    assert got.code == MEASURE_AFTER
    assert got.basis == "completed"
    assert got.basis_text == "실측완료 표시"
    assert got.date == ""
    assert got.text == "실측 후"
    assert got.notice == "실측을 마친 뒤입니다."


def test_measurement_completed_carries_past_date_when_available():
    """실측완료 표시가 이겨도 과거 날짜가 있으면 그 날짜를 곁들인다."""
    got = judge_measure_progress(
        _order(dates=["2026-08-20", "2026-09-02"], measurement_completed=True),
        today=TODAY,
    )
    assert got.code == MEASURE_AFTER
    assert got.basis == "completed"
    assert got.date == "2026-09-02"


def test_stage_past_measure_without_date_is_after():
    """단계가 실측을 지났으면(도면) 날짜가 없어도 실측 후다."""
    got = judge_measure_progress(_order(status="DRAWING"), today=TODAY)
    assert got.code == MEASURE_AFTER
    assert got.basis == "stage"
    assert got.basis_text == "진행 단계"
    assert got.date == ""
    assert got.text == "실측 후"


def test_korean_stage_name_folds_to_after():
    """한글 단계 값(도면)도 같은 축으로 접힌다."""
    got = judge_measure_progress(_order(workflow_stage="도면"), today=TODAY)
    assert got.code == MEASURE_AFTER
    assert got.basis == "stage"


def test_as_stage_is_after():
    """AS 계열 단계는 실측을 한참 지난 자리다."""
    got = judge_measure_progress(_order(status="AS_RECEIVED"), today=TODAY)
    assert got.code == MEASURE_AFTER
    assert got.basis == "stage"


def test_measure_stage_itself_is_not_after():
    """실측 단계 자체는 지난 것이 아니다 — 날짜가 판정한다."""
    got = judge_measure_progress(
        _order(status="MEASURE", dates=["2026-09-12"]), today=TODAY)
    assert got.code == MEASURE_BEFORE
    assert got.basis == "schedule"


def test_unknown_stage_abstains_and_dates_decide():
    """모르는 단계는 RECEIVED 로 접지 않고 이 축을 기권한다."""
    future = judge_measure_progress(
        _order(status="ZZ_UNKNOWN_STAGE", dates=["2026-09-12"]), today=TODAY)
    assert future.code == MEASURE_BEFORE
    assert future.basis == "schedule"

    blank = judge_measure_progress(_order(status="ZZ_UNKNOWN_STAGE"), today=TODAY)
    assert blank.code == MEASURE_NONE
    assert blank.basis == "unknown"


def test_workflow_stage_beats_status():
    """structured_data workflow.stage 가 Order.status 보다 우선한다."""
    got = judge_measure_progress(
        _order(status="RECEIVED", workflow_stage="PRODUCTION"), today=TODAY)
    assert got.code == MEASURE_AFTER
    assert got.basis == "stage"


def test_mixed_past_and_future_is_after_with_latest_past_date():
    """여러 일정 중 하나라도 과거면 이미 나간 것이다(비용이 나갔다)."""
    got = judge_measure_progress(
        _order(dates=["2026-08-20", "2026-09-02", "2026-09-20"]), today=TODAY)
    assert got.code == MEASURE_AFTER
    assert got.basis == "schedule"
    assert got.date == "2026-09-02"


def test_earliest_future_date_is_used_for_before():
    """전부 미래면 가장 이른 날짜를 예정일로 쓴다."""
    got = judge_measure_progress(
        _order(dates=["2026-10-01", "2026-09-12"]), today=TODAY)
    assert got.code == MEASURE_BEFORE
    assert got.date == "2026-09-12"


def test_today_argument_moves_the_verdict():
    """같은 주문도 기준일이 바뀌면 판정이 바뀐다."""
    order = _order(dates=["2026-09-10"])
    assert judge_measure_progress(order, today=datetime.date(2026, 9, 7)).code == MEASURE_BEFORE
    assert judge_measure_progress(order, today=datetime.date(2026, 9, 11)).code == MEASURE_AFTER


def test_legacy_column_date_is_read_through_canonical_reader():
    """싱크 컬럼만 있는 주문도 정본 리더를 통해 읽힌다(직접 읽지 않는다)."""
    got = judge_measure_progress(
        _order(measurement_date="2026-09-02", is_erp_order=False), today=TODAY)
    assert got.code == MEASURE_AFTER
    assert got.date == "2026-09-02"


def test_default_today_uses_kst_today():
    """today 를 안 주면 KST 오늘로 판정한다(호출만으로 터지지 않는다)."""
    got = judge_measure_progress(_order())
    assert got.code == MEASURE_NONE


def test_source_never_reads_measurement_time_or_sync_column():
    """``measurement_time`` 은 ERP 주문에서 전부 NULL 이고, 싱크 컬럼은 첫 날짜만 담는다.

    둘 다 판정 근거로 쓰면 안 되므로 코드가 그 속성을 **직접** 읽지 않는지 AST 로 본다
    (설명하는 주석·docstring 은 세지 않는다).
    """
    tree = ast.parse(Path(mp.__file__).read_text(encoding="utf-8"))
    attribute_reads = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    getattr_reads = {
        node.args[1].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    }
    touched = attribute_reads | getattr_reads
    assert "measurement_time" not in touched
    assert "measurement_date" not in touched
