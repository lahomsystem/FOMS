"""PRODUCTION-BACKFILL-00 PostgreSQL 계약 테스트 (PGTEST-00 lane).

생산 실행 UUID run registry(:class:`~models.ProductionRun`)와 flat→run 매핑 backfill 을
실 PostgreSQL 로 검증한다:

* flat steps/defects/history → current ``IN_PROGRESS`` run 보존(유실 0·flat 잔존).
* in-flight PRODUCTION current IN_PROGRESS **100% 매핑**(coverage).
* ambiguous(복수 start·rework·past-production)는 자동 매핑 0 → 수동 CSV.
* backfill 멱등·resume·enforcement 게이트.
* UUID DB-global unique·order binding·current run partial-unique(1개).

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip(conftest). 커밋 파일에 비밀번호 0
(dev DSN 은 env). 이 packet 은 아직 route/전이에 배선되지 않았다(PRODUCTION-BACKFILL-00
경계) — 이 테스트가 하류(STATE-PROD-01)가 의존할 계약을 정본으로 고정한다.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from foms.services.orders.audit_production_runs import (
    MULTIPLE_STARTS,
    PAST_PRODUCTION,
    ProductionRunAudit,
    ProductionRunPlan,
    audit_production_runs,
    classify_order,
    to_manual_csv,
)
from foms.services.orders.backfill_production_runs import (
    apply_safe_backfill,
    can_enforce,
)
from models import Order, ProductionRun


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _sd(stage, *, starts=1, rework=0, steps_done=1, defects=1, note="제작 시작"):
    """production 시나리오 structured_data 를 만든다.

    Args:
        stage: workflow.stage (main-stage 판정용).
        starts: workflow.history 의 PRODUCTION 진입 수.
        rework: production.rework.count (0 이면 rework 미기록).
        steps_done: done=True 로 표시할 step 수(생산 활동 신호).
        defects: defects 항목 수.
        note: 첫 history 항목 note.
    """
    history = [
        {"stage": "PRODUCTION", "updated_at": f"2026-07-24T0{i}:00:00",
         "updated_by": "u", "note": note}
        for i in range(1, starts + 1)
    ]
    steps = [
        {"key": "cut", "label": "재단", "done": i < steps_done,
         "at": "2026-07-24T01:00:00", "by_name": "u"}
        for i in range(2)
    ]
    prod = {"steps": steps,
            "defects": [{"reason": "파손", "at": "2026-07-24T01:00:00", "by_name": "u"}
                        for _ in range(defects)]}
    if rework:
        prod["rework"] = {"active": True, "reason": "재작업", "count": rework,
                          "at": "2026-07-24T02:00:00", "by_name": "u"}
    return {"workflow": {"stage": stage, "history": history}, "production": prod}


def _order(session, sd) -> Order:
    """ERP 주문 1건 생성."""
    o = Order(
        received_date="2026-07-24", customer_name="홍길동", phone="010-0000-0000",
        address="서울", product="침대", is_erp_order=True, structured_data=sd,
    )
    session.add(o)
    session.flush()
    return o


# --------------------------------------------------------------------------- #
# 분류: SAFE / ambiguous / 대상 제외
# --------------------------------------------------------------------------- #
def test_classify_in_flight_single_start_is_safe(pg_session):
    """in-flight PRODUCTION·단일 start·rework 0 → SAFE IN_PROGRESS plan(steps/defects 스냅샷)."""
    order = _order(pg_session, _sd("PRODUCTION", starts=1, rework=0, steps_done=2, defects=2))
    plan = classify_order(order)
    assert isinstance(plan, ProductionRunPlan)
    assert plan.order_id == order.id
    assert plan.status == "IN_PROGRESS"
    assert plan.started_at == "2026-07-24T01:00:00"
    assert len(plan.steps) == 2 and plan.steps[0]["key"] == "cut"
    assert len(plan.defects) == 2


def test_classify_rework_is_ambiguous(pg_session):
    """rework(복수 run)은 flat scope 소실이라 자동 매핑 불가 → MULTIPLE_STARTS."""
    order = _order(pg_session, _sd("PRODUCTION", starts=2, rework=1))
    amb = classify_order(order)
    assert amb.reason == MULTIPLE_STARTS
    assert amb.order_id == order.id


def test_classify_past_production_is_ambiguous(pg_session):
    """main 이 PRODUCTION 을 지남(시공) → 직접 COMPLETED 자동 추론 금지 → PAST_PRODUCTION."""
    order = _order(pg_session, _sd("CONSTRUCTION", starts=1))
    amb = classify_order(order)
    assert amb.reason == PAST_PRODUCTION


def test_classify_no_activity_is_excluded(pg_session):
    """생산 데이터 없음 / 활동 0 → 대상 제외(None)."""
    order = _order(pg_session, {"workflow": {"stage": "RECEIVED", "history": []}})
    assert classify_order(order) is None
    # production 키는 있으나 done 0·defect 0·start 0 → 활동 없음.
    idle = _order(pg_session, {"workflow": {"stage": "RECEIVED", "history": []},
                               "production": {"steps": [{"key": "cut", "done": False}],
                                              "defects": []}})
    assert classify_order(idle) is None


# --------------------------------------------------------------------------- #
# backfill: SAFE 만 발급 + flat 보존 + 자동 매핑 0
# --------------------------------------------------------------------------- #
def test_backfill_mints_run_and_preserves_flat(pg_session):
    """SAFE 주문에 IN_PROGRESS run 발급, flat structured_data 는 무변경(보존)."""
    order = _order(pg_session, _sd("PRODUCTION", steps_done=2, defects=1))
    before = order.structured_data

    result = apply_safe_backfill(pg_session)
    pg_session.expire_all()

    assert result.runs_minted == 1
    assert result.ambiguous_skipped == 0

    run = pg_session.query(ProductionRun).filter_by(order_id=order.id).one()
    assert run.status == "IN_PROGRESS"
    assert run.is_current is True
    assert uuid.UUID(run.id)
    assert run.started_at is not None
    assert len(run.steps) == 2               # flat steps 복제
    assert len(run.defects) == 1

    # flat 은 그대로 남아 있다(삭제 금지).
    reloaded = pg_session.get(Order, order.id).structured_data
    assert reloaded["production"]["steps"] == before["production"]["steps"]
    assert reloaded["production"]["defects"] == before["production"]["defects"]
    assert reloaded["workflow"]["history"] == before["workflow"]["history"]


def test_backfill_skips_ambiguous(pg_session):
    """ambiguous(rework·past) 주문은 run 을 발급하지 않는다(자동 매핑 0)."""
    _order(pg_session, _sd("PRODUCTION", starts=2, rework=1))   # ambiguous
    _order(pg_session, _sd("CONSTRUCTION", starts=1))            # ambiguous

    result = apply_safe_backfill(pg_session)
    pg_session.expire_all()

    assert result.runs_minted == 0
    assert result.ambiguous_skipped == 2
    assert pg_session.query(ProductionRun).count() == 0


def test_manual_csv_lists_ambiguous_only(pg_session):
    """ambiguous 는 §1376 컬럼 CSV 로 내보내진다(target/approved 는 공란·decision=MANUAL)."""
    order = _order(pg_session, _sd("PRODUCTION", starts=2, rework=1))
    csv_text = to_manual_csv(audit_production_runs(pg_session))
    assert ("order_id,legacy_started_at,legacy_steps_json,legacy_defects_json,"
            "target_run_id,target_status,decision,reason,approved_by_user_id") in csv_text
    assert f"{order.id}," in csv_text
    assert f",MANUAL,{MULTIPLE_STARTS}," in csv_text


# --------------------------------------------------------------------------- #
# in-flight PRODUCTION current IN_PROGRESS 100% 매핑
# --------------------------------------------------------------------------- #
def test_in_flight_maps_to_in_progress_100pct(pg_session):
    """모든 in-flight PRODUCTION(단일 start)이 IN_PROGRESS run 으로 100% 매핑된다."""
    ids = [_order(pg_session, _sd("PRODUCTION")).id for _ in range(3)]
    audit = audit_production_runs(pg_session)
    assert audit.in_flight_ids == set(ids)
    assert audit.covers_all_in_flight() is True

    apply_safe_backfill(pg_session, audit=audit)
    pg_session.expire_all()
    for oid in ids:
        run = pg_session.query(ProductionRun).filter_by(order_id=oid, is_current=True).one()
        assert run.status == "IN_PROGRESS"


def test_coverage_incomplete_when_in_flight_ambiguous(pg_session):
    """in-flight 인데 rework 로 ambiguous 면 coverage < 100%."""
    _order(pg_session, _sd("PRODUCTION"))                        # safe in-flight
    _order(pg_session, _sd("PRODUCTION", starts=2, rework=1))    # ambiguous in-flight
    audit = audit_production_runs(pg_session)
    assert len(audit.in_flight_ids) == 2
    assert audit.covers_all_in_flight() is False


# --------------------------------------------------------------------------- #
# 멱등 / resume
# --------------------------------------------------------------------------- #
def test_backfill_is_idempotent(pg_session):
    """재실행 시 이미 current run 이 있는 주문은 다시 발급하지 않는다."""
    _order(pg_session, _sd("PRODUCTION"))
    first = apply_safe_backfill(pg_session)
    assert first.runs_minted == 1

    pg_session.expire_all()
    second = apply_safe_backfill(pg_session)
    assert second.runs_minted == 0
    assert second.already_present == 1
    assert pg_session.query(ProductionRun).count() == 1


def test_backfill_resumes_after_partial(pg_session):
    """부분 적용(한 주문만) 후 재실행이 남은 주문을 이어서 발급한다(중복 0)."""
    o1 = _order(pg_session, _sd("PRODUCTION"))
    o2 = _order(pg_session, _sd("PRODUCTION"))

    plan1 = classify_order(pg_session.get(Order, o1.id))
    partial = ProductionRunAudit(safe=(plan1,), ambiguous=(), in_flight_ids=frozenset({o1.id}))
    apply_safe_backfill(pg_session, audit=partial)
    pg_session.expire_all()
    assert pg_session.query(ProductionRun).filter_by(order_id=o1.id).count() == 1
    assert pg_session.query(ProductionRun).filter_by(order_id=o2.id).count() == 0

    result = apply_safe_backfill(pg_session)
    pg_session.expire_all()
    assert result.runs_minted == 1                              # o2 만 신규
    assert result.already_present == 1                          # o1 은 이미 있음
    assert pg_session.query(ProductionRun).filter_by(order_id=o2.id).count() == 1


# --------------------------------------------------------------------------- #
# enforcement 게이트
# --------------------------------------------------------------------------- #
def test_enforcement_gate_blocks_with_ambiguous(pg_session):
    """ambiguous 가 있으면 enforcement 게이트가 닫힌다."""
    _order(pg_session, _sd("PRODUCTION"))
    _order(pg_session, _sd("PRODUCTION", starts=2, rework=1))   # ambiguous
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    assert can_enforce(pg_session) is False


def test_enforcement_gate_allows_when_clean(pg_session):
    """ambiguous 0 + 모든 in-flight IN_PROGRESS 100% 면 enforcement 가능."""
    _order(pg_session, _sd("PRODUCTION"))
    _order(pg_session, _sd("PRODUCTION"))
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    assert can_enforce(pg_session) is True


def test_enforcement_gate_blocks_before_backfill(pg_session):
    """in-flight 주문이 있는데 run 미발급이면(backfill 전) 게이트가 닫힌다."""
    _order(pg_session, _sd("PRODUCTION"))
    assert can_enforce(pg_session) is False


# --------------------------------------------------------------------------- #
# DB 제약: UUID unique · order binding · current run 1개
# --------------------------------------------------------------------------- #
def test_current_run_partial_unique(pg_session):
    """한 주문에 current run 은 최대 1개(partial unique) — 2번째 current 는 거부, 이력은 허용."""
    order = _order(pg_session, _sd("PRODUCTION"))
    apply_safe_backfill(pg_session)
    pg_session.expire_all()

    # 같은 주문에 2번째 current run 삽입 → partial unique 위반(DB 직격).
    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            pg_session.execute(ProductionRun.__table__.insert().values(
                id=str(uuid.uuid4()), order_id=order.id, status="IN_PROGRESS", is_current=True,
            ))

    # 종결된 run(is_current=False)은 같은 주문에 여러 개 허용(이력).
    with pg_session.begin_nested():
        pg_session.execute(ProductionRun.__table__.insert().values(
            id=str(uuid.uuid4()), order_id=order.id, status="SUPERSEDED", is_current=False,
        ))
    assert pg_session.query(ProductionRun).filter_by(order_id=order.id).count() == 2


def test_uuid_pk_global_unique(pg_session):
    """같은 UUID 재삽입은 PK 위반(DB-global unique)."""
    order = _order(pg_session, _sd("PRODUCTION"))
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    existing = pg_session.query(ProductionRun).filter_by(order_id=order.id).one()

    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            pg_session.execute(ProductionRun.__table__.insert().values(
                id=existing.id, order_id=order.id, status="SUPERSEDED", is_current=False,
            ))
