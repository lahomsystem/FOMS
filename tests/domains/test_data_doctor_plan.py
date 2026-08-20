"""data doctor 복구안 산출 로직 — DATA-DOCTOR-01 순수 함수 계약.

DB 없이 검증 가능한 부분(증거 병합·복구안 조립)만 잠근다. 적용/롤백은 실 DSN 이 필요해
스테이징 실행으로 검증한다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[2] / "tools" / "ops" / "data_doctor.py"
_spec = importlib.util.spec_from_file_location("data_doctor", _MODULE_PATH)
data_doctor = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(data_doctor)


def test_merge_evidence_prefers_higher_confidence():
    """exact(스냅샷) > logged(감사행) > event > inferred 순으로 이긴다."""
    inferred = {1: {"before": "AS_RECEIVED", "confidence": "inferred", "source": "as_history"}}
    logged = {1: {"before": "AS_COMPLETED", "confidence": "logged", "source": "security_logs"}}
    merged = data_doctor._merge_evidence(inferred, logged)
    assert merged[1]["before"] == "AS_COMPLETED"
    assert merged[1]["confidence"] == "logged"

    snapshot = {1: {"before": "AS", "confidence": "exact", "source": "pitr"}}
    merged2 = data_doctor._merge_evidence(inferred, logged, snapshot)
    assert merged2[1]["before"] == "AS"
    assert merged2[1]["confidence"] == "exact"


def test_merge_evidence_fills_missing_fields_from_lower_layer():
    """상위 층에 없는 필드(stage_before)는 하위 층 값으로 보충한다."""
    event = {7: {"stage_before": "MEASURE", "confidence": "event", "source": "events"}}
    logged = {7: {"before": "AS_RECEIVED", "confidence": "logged", "source": "logs"}}
    merged = data_doctor._merge_evidence(event, logged)
    assert merged[7]["before"] == "AS_RECEIVED"
    assert merged[7]["stage_before"] == "MEASURE"


def test_build_plan_items_skips_unrecoverable_and_already_correct():
    """근거 없음·이미 정상인 행은 복구 대상에서 빠지고 사유가 남는다."""
    current = {
        1: {"id": 1, "customer_name": "가", "status": "COMPLETED", "erp_stage_code": "COMPLETED"},
        2: {"id": 2, "customer_name": "나", "status": "COMPLETED", "erp_stage_code": "COMPLETED"},
        3: {"id": 3, "customer_name": "다", "status": "AS_RECEIVED", "erp_stage_code": "MEASURE"},
    }
    evidence = {
        1: {"before": "AS_RECEIVED", "stage_before": "MEASURE", "confidence": "logged"},
        3: {"before": "AS_RECEIVED", "confidence": "logged"},
    }
    items, skipped = data_doctor._build_plan_items(current, evidence, only_as=False)
    assert [i["order_id"] for i in items] == [1]
    assert items[0]["restore_status"] == "AS_RECEIVED"
    assert items[0]["restore_stage"] == "MEASURE"
    reasons = {s["order_id"]: s["reason"] for s in skipped}
    assert "근거 없음" in reasons[2]
    assert "이미" in reasons[3]


def test_build_plan_items_only_as_filter():
    """--only-as 는 AS overlay 복구만 남긴다(일반 단계 되돌리기는 제외)."""
    current = {
        1: {"id": 1, "customer_name": "가", "status": "COMPLETED", "erp_stage_code": "COMPLETED"},
        2: {"id": 2, "customer_name": "나", "status": "COMPLETED", "erp_stage_code": "COMPLETED"},
    }
    evidence = {
        1: {"before": "AS_COMPLETED", "confidence": "logged"},
        2: {"before": "CONSTRUCTION", "confidence": "logged"},
    }
    items, skipped = data_doctor._build_plan_items(current, evidence, only_as=True)
    assert [i["order_id"] for i in items] == [1]
    assert any("AS 대상 아님" in s["reason"] for s in skipped)


def test_confidence_rank_covers_all_sources():
    """증거 층이 늘어나도 랭크 표가 비지 않게 계약으로 잠근다."""
    assert set(data_doctor.CONFIDENCE_RANK) == {"inferred", "event", "logged", "exact"}
    assert data_doctor.CONFIDENCE_RANK["exact"] > data_doctor.CONFIDENCE_RANK["logged"]
