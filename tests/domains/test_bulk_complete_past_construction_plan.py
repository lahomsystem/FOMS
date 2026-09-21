"""시공일 지난 적체 주문 일괄 완료 — 순수 판정 계약(BACKLOG-COMPLETE-01).

DB 없이 검증 가능한 부분(분류·plan 조립·workflow 변환)만 잠근다.
apply/rollback 은 ``tests/postgres/test_bulk_complete_past_construction_pg.py`` 가 PG 레인에서 검증한다.
"""

from __future__ import annotations

import importlib.util
from datetime import date, datetime
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[2] / "tools" / "ops" / "bulk_complete_past_construction.py"
_spec = importlib.util.spec_from_file_location("bulk_complete_past_construction", _MODULE_PATH)
mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mod)


def _row(**over):
    base = {
        "id": 1, "customer_name": "가", "status": "MEASURE", "is_erp_order": True,
        "erp_stage_code": "MEASURE", "erp_construction_date": "2026-08-20",
        "as_axis_status": None, "meta_draft": False, "open_quests": 0,
        "naver_claim_open": False,
    }
    base.update(over)
    return base


def test_main_row_when_no_as_axis():
    """AS 축 없는 본공정 건은 main(status 까지 COMPLETED)."""
    mode, reason, flags = mod.classify_row(_row())
    assert (mode, reason, flags) == ("main", None, [])


def test_as_tab_rows_are_stage_only():
    """AS 탭 건(축 값 또는 AS overlay status)은 stage 만 — 미완료·완료 탭 모두."""
    for over in (
        {"as_axis_status": "RECEIVED", "status": "AS_RECEIVED"},
        {"as_axis_status": "COMPLETED", "status": "AS_COMPLETED"},
        {"as_axis_status": "IN_PROGRESS", "status": "AS"},
        {"as_axis_status": None, "status": "AS_RECEIVED"},  # 비축 레거시 overlay 도 보호
    ):
        mode, reason, _ = mod.classify_row(_row(**over))
        assert (mode, reason) == ("as_stage_only", None), over


def test_skip_reasons_negative_controls():
    """제외 5종 + 초안·날짜 형식 — 각각 사유가 붙고 대상에서 빠진다."""
    cases = {
        "non_erp": _row(is_erp_order=False),
        "draft": _row(status="DRAFT"),
        "draft_meta": _row(meta_draft=True),
        "on_hold": _row(status="ON_HOLD"),
        "logistics_in_flight": _row(status="SCHEDULED"),
        "logistics_in_flight2": _row(status="SHIPPED_PENDING"),
        "naver_claim_open": _row(naver_claim_open=True),
        "stage_not_main": _row(erp_stage_code="AS_RECEIVED", status="AS_RECEIVED"),
        "stage_not_main2": _row(erp_stage_code="COMPLETED", status="COMPLETED"),
        "construction_date_malformed": _row(erp_construction_date="2026/08/20"),
    }
    expected = {
        "non_erp": "non_erp", "draft": "draft", "draft_meta": "draft", "on_hold": "on_hold",
        "logistics_in_flight": "logistics_in_flight", "logistics_in_flight2": "logistics_in_flight",
        "naver_claim_open": "naver_claim_open", "stage_not_main": "stage_not_main",
        "stage_not_main2": "stage_not_main",
        "construction_date_malformed": "construction_date_malformed",
    }
    for key, row in cases.items():
        mode, reason, _ = mod.classify_row(row)
        assert mode is None and reason == expected[key], key


def test_flags_old_construction_and_open_quests():
    """옛 시공일·열린 quest 는 처리하되 표식이 붙는다."""
    mode, reason, flags = mod.classify_row(_row(erp_construction_date="2025-10-01", open_quests=2))
    assert mode == "main" and reason is None
    assert flags == ["old_construction_date", "open_quests"]


def test_cutoff_boundary():
    """cutoff 는 오늘-7일 ISO 이고, 시공일 < cutoff 만 후보(SQL 술어와 같은 축)."""
    assert mod.cutoff_iso(date(2026, 9, 22), 7) == "2026-09-15"


def test_build_plan_summary_and_to_status():
    """plan 은 mode 별 집계·제외 사유·to_status 를 담는다."""
    rows = [
        _row(id=1),
        _row(id=2, as_axis_status="RECEIVED", status="AS_RECEIVED"),
        _row(id=3, status="ON_HOLD"),
        _row(id=4, erp_stage_code="DRAWING", status="DRAWING"),
    ]
    plan = mod.build_plan(rows, cutoff="2026-09-15", today="2026-09-22", cutoff_days=7)
    by_id = {i["order_id"]: i for i in plan["items"]}
    assert set(by_id) == {1, 2, 4}
    assert by_id[1]["to_status"] == "COMPLETED"
    assert by_id[2]["to_status"] == "AS_RECEIVED"  # AS 탭 건 status 불변
    assert by_id[2]["mode"] == "as_stage_only"
    assert plan["skipped"] == [{
        "order_id": 3, "customer_name": "가", "observed_status": "ON_HOLD",
        "observed_stage": "MEASURE", "observed_as_axis": None,
        "construction_date": "2026-08-20", "reason": "on_hold",
    }]
    s = plan["summary"]
    assert s["main"] == 2 and s["as_stage_only"] == 1 and s["skipped"] == {"on_hold": 1}
    assert s["by_stage"] == {"MEASURE/main": 1, "MEASURE/as_stage_only": 1, "DRAWING/main": 1}


def test_completed_workflow_keeps_other_keys_and_marks_override():
    """stage·stage_updated_at·stage_override 만 바뀌고 나머지 키·원본은 그대로."""
    original = {"stage": "MEASURE", "stage_updated_at": "2026-08-01T00:00:00",
                "measurement_date": "2026-08-10", "history": [{"a": 1}]}
    now = datetime(2026, 9, 22, 3, 0, 0)
    out = mod.completed_workflow(original, now=now)
    assert original["stage"] == "MEASURE"
    assert out["stage"] == "COMPLETED"
    assert out["stage_updated_at"] == "2026-09-22T03:00:00"
    assert out["stage_override"] == {
        "at": "2026-09-22T03:00:00", "stage": "COMPLETED", "batch": mod.BATCH_ID,
        "measurement_date": "2026-08-10",
    }
    assert out["history"] is original["history"]
    assert mod.completed_workflow(None, now=now)["stage"] == "COMPLETED"


def test_open_claim_statuses_match_mapping_phases():
    """열린 클레임 집합은 앱의 CLAIM_PHASES 요청·처리중과 같아야 한다(두 벌 드리프트 방지)."""
    from foms.services.integrations.naver_commerce.mapping import (
        CLAIM_PHASE_PROGRESS, CLAIM_PHASE_REQUESTED, CLAIM_PHASES,
    )
    expected = {k for k, v in CLAIM_PHASES.items() if v in (CLAIM_PHASE_REQUESTED, CLAIM_PHASE_PROGRESS)}
    assert set(mod.OPEN_CLAIM_STATUSES) == expected
