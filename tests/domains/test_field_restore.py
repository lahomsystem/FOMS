"""필드 단위 복원 판정 테스트 (RESTORE-GUI-01 T1).

DB 없이 판정 규칙만 본다 — 거부 조건 4개가 각각 제 이유로 막는지, 그리고 화이트리스트가
감사 대상 경로를 벗어나지 않는지(계약).
"""

import pytest

from foms.services.orders.field_restore import (
    RESTORABLE_PATHS,
    RestoreRejected,
    describe_restorability,
    plan_restore,
    write_path,
)
from foms.services.orders.order_field_change_writer import ledger_text
from foms.services.orders.structured_diff import SCALAR_PATHS
from models import OrderFieldChange


def _row(path: str, before: str | None, after: str | None) -> OrderFieldChange:
    """판정에 필요한 필드만 채운 원장 행(세션에 붙이지 않는다)."""
    return OrderFieldChange(
        id=1,
        change_set_id="cs-1",
        order_id=1,
        path=path,
        path_template=path,
        op="set",
        before_value=before,
        after_value=after,
        actor_user_id=7,
    )


def _sd(path: str, value):
    """점 경로 하나만 채운 structured_data."""
    sd: dict = {}
    node = sd
    parts = path.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value
    return sd


def test_whitelist_is_subset_of_audited_paths():
    """복원 가능 경로는 감사 대상 경로를 벗어날 수 없다(원장에 근거가 없으면 복원도 없다)."""
    assert RESTORABLE_PATHS <= set(SCALAR_PATHS)


def test_rejects_path_outside_whitelist():
    """화이트리스트 밖 경로는 400 — 파생·PII 축을 값 되쓰기로 만지지 않는다."""
    row = _row("totals.items_total", "1000", "2000")
    with pytest.raises(RestoreRejected) as excinfo:
        plan_restore(row, _sd("totals.items_total", "2000"))
    assert excinfo.value.status_code == 400


def test_rejects_truncated_value():
    """절단된 값(…)은 400 — 되쓰면 복원이 곧 데이터 훼손이다."""
    path = "flags.urgent_reason"
    row = _row(path, "가" * 120 + "…", "짧은값")
    with pytest.raises(RestoreRejected) as excinfo:
        plan_restore(row, _sd(path, "짧은값"))
    assert excinfo.value.status_code == 400


def test_rejects_non_string_current_value():
    """현재 값이 문자열 축이 아니면 400 — 원장은 정규화 문자열만 담아 원형 복원이 불가하다."""
    path = "shipment.trip"
    row = _row(path, "1", "2")
    with pytest.raises(RestoreRejected) as excinfo:
        plan_restore(row, _sd(path, {"count": 2}))
    assert excinfo.value.status_code == 400


def test_rejects_when_value_changed_again():
    """그 변경 이후 값이 또 바뀌었으면 409 — 남이 고친 값을 덮지 않는다."""
    path = "schedule.measurement.date"
    row = _row(path, "2026-08-12", "2026-08-14")
    with pytest.raises(RestoreRejected) as excinfo:
        plan_restore(row, _sd(path, "2026-08-20"))
    assert excinfo.value.status_code == 409


def test_rejects_when_already_restored():
    """이미 그 값이면 409 — 같은 되돌리기를 두 번 기록하지 않는다."""
    path = "schedule.construction.date"
    row = _row(path, "2026-08-12", "2026-08-12")
    with pytest.raises(RestoreRejected) as excinfo:
        plan_restore(row, _sd(path, "2026-08-12"))
    assert excinfo.value.status_code == 409


def test_accepts_valid_restore_and_reports_plan():
    """정상 건은 경로·이전값·현재값을 담은 복원안을 돌려준다."""
    path = "schedule.measurement.date"
    row = _row(path, "2026-08-12", "2026-08-14")
    plan = plan_restore(row, _sd(path, "2026-08-14"))
    assert plan == {
        "path": path,
        "before": "2026-08-12",
        "after": "2026-08-14",
        "current": "2026-08-14",
    }


def test_empty_before_is_restorable_as_clear():
    """이전이 빈값이면 빈값으로 되돌린다(키를 지우지 않는다 — 모양 유지)."""
    path = "flags.urgent_reason"
    row = _row(path, None, "급함")
    plan = plan_restore(row, _sd(path, "급함"))
    assert plan["before"] is None

    sd = _sd(path, "급함")
    write_path(sd, path, plan["before"])
    assert sd["flags"]["urgent_reason"] == ""
    assert ledger_text(sd["flags"]["urgent_reason"], path) is None


def test_write_path_creates_missing_nodes():
    """중간 노드가 없거나 dict 가 아니면 만들어 쓴다."""
    sd = {"schedule": {"measurement": "손상된값"}}
    write_path(sd, "schedule.measurement.date", "2026-08-12")
    assert sd["schedule"]["measurement"]["date"] == "2026-08-12"


def test_describe_restorability_reports_reason_without_raising():
    """화면용 판정은 예외 대신 이유 문자열을 돌려준다(버튼을 미리 끈다)."""
    row = _row("notes", "긴 메모", "다른 메모")
    result = describe_restorability(row, {"notes": "다른 메모"})
    assert result["restorable"] is False
    assert result["reason"]
