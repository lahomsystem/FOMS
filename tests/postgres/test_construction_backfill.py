"""CONSTRUCTION-BACKFILL-00 PostgreSQL 계약 테스트 (PGTEST-00 lane).

시공 실행 UUID attempt registry(:class:`~models.OrderConstructionAttempt`)와 flat→attempt
매핑 backfill 을 실 PostgreSQL 로 검증한다:

* flat 시공 시작 history/예정일/evidence → attempt safe map(유실 0·flat 잔존).
* current attempt 0/1(복수 시작·재작업 → ambiguous).
* ambiguous(복수 시작·재작업·직접 COMPLETED·시작 누락·malformed)는 자동 매핑 0 → 수동 CSV.
* dry-run(write 0)·apply(**명시 승인 필수** — command flag ON 거부)·verify(100%).
* in-flight CONSTRUCTION current **100% 매핑**(coverage)·backfill 멱등·resume·enforcement 게이트.
* UUID DB-global unique·order binding·current attempt partial-unique(1개)·legacy 멱등 unique.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip(conftest). 커밋 파일에 비밀번호 0
(dev DSN 은 env). 이 packet 은 아직 route/전이에 배선되지 않았다(CONSTRUCTION-BACKFILL-00
경계 — inferred stage rewrite·직접 COMPLETED 추론 금지) — 이 테스트가 하류(STATE-CONST-CS)가
의존할 계약을 정본으로 고정한다.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from foms.services.orders.audit_construction_attempts import (
    MALFORMED,
    MISSING_START,
    MULTIPLE_STARTS,
    PAST_CONSTRUCTION,
    AmbiguousConstructionAttempt,
    ConstructionAttemptPlan,
    audit_construction_attempts,
    classify_order,
    to_manual_csv,
)
from foms.services.orders.backfill_construction_attempts import (
    APPROVAL_TOKEN,
    ApprovalRequiredError,
    apply_safe_backfill,
    can_enforce,
    dry_run,
    verify,
)
from models import Order, OrderConstructionAttempt


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _start_entry(seq=1):
    """시공 시작(construction start) workflow.history entry."""
    return {
        "stage": "CONSTRUCTION",
        "updated_at": f"2026-07-2{seq}T09:00:00",
        "updated_by": "기사A",
        "note": "시공 시작",
    }


def _fail_entry(fail_id):
    """시공 불가(재작업) construction_fail_history entry."""
    return {
        "id": fail_id,
        "failed_at": f"2026-07-2{fail_id}T18:00:00",
        "failed_by": "기사B",
        "reason": "site_issue",
        "detail": "현장 진입 불가",
        "reschedule_date": "2026-08-01",
        "previous_stage": "CONSTRUCTION",
    }


def _sd(stage, *, history=None, fail_history=None, scheduled_date=None, evidence=None):
    """order.structured_data 구성(workflow.stage = main-stage 원천)."""
    sd = {"workflow": {"stage": stage, "history": history or []}}
    if fail_history is not None:
        sd["construction_fail_history"] = fail_history
    if scheduled_date is not None:
        sd["schedule"] = {"construction": {"date": scheduled_date}}
    if evidence is not None:
        sd.setdefault("construction", {})["evidence"] = evidence
    return sd


def _order(session, stage, **sd_kwargs) -> Order:
    """ERP 주문 1건 생성(workflow.stage = main-stage 원천)."""
    o = Order(
        received_date="2026-07-24", customer_name="홍길동", phone="010-0000-0000",
        address="서울", product="침대", is_erp_order=True, status=stage,
        structured_data=_sd(stage, **sd_kwargs),
    )
    session.add(o)
    session.flush()
    return o


# --------------------------------------------------------------------------- #
# 분류: SAFE / ambiguous / 대상 제외
# --------------------------------------------------------------------------- #
def test_classify_single_start_is_safe_current(pg_session):
    """in-flight CONSTRUCTION·시공 시작 1·재작업 0 → SAFE current IN_PROGRESS, 스냅샷 복제."""
    evidence = {"before": [1], "after": [2, 3], "signature_att_id": 9}
    order = _order(pg_session, "CONSTRUCTION", history=[_start_entry(1)],
                   scheduled_date="2026-07-30", evidence=evidence)
    plan = classify_order(order)
    assert isinstance(plan, ConstructionAttemptPlan)
    assert plan.order_id == order.id
    assert plan.status == "IN_PROGRESS"
    assert plan.legacy_seq == 0
    assert plan.started_at == "2026-07-21T09:00:00" and plan.started_by == "기사A"
    assert plan.scheduled_date == "2026-07-30"
    assert plan.evidence == evidence


def test_classify_multiple_starts_is_ambiguous(pg_session):
    """시공 시작 복수 → attempt 경계 소실 → MULTIPLE_STARTS(자동 분리 금지)."""
    order = _order(pg_session, "CONSTRUCTION", history=[_start_entry(1), _start_entry(2)])
    amb = classify_order(order)
    assert isinstance(amb, AmbiguousConstructionAttempt)
    assert amb.reason == MULTIPLE_STARTS
    assert amb.start_count == 2 and amb.order_id == order.id


def test_classify_with_rework_is_ambiguous(pg_session):
    """in-flight 인데 construction_fail_history(재작업) 존재 → MULTIPLE_STARTS."""
    order = _order(pg_session, "CONSTRUCTION", history=[_start_entry(1)],
                   fail_history=[_fail_entry(1)])
    amb = classify_order(order)
    assert isinstance(amb, AmbiguousConstructionAttempt)
    assert amb.reason == MULTIPLE_STARTS
    assert amb.fail_count == 1


def test_classify_completed_is_past_construction(pg_session):
    """main==COMPLETED(시공 완료 이력)인데 시공 시작 존재 → PAST_CONSTRUCTION(직접 COMPLETED 자동 금지)."""
    order = _order(pg_session, "COMPLETED", history=[_start_entry(1)])
    amb = classify_order(order)
    assert isinstance(amb, AmbiguousConstructionAttempt)
    assert amb.reason == PAST_CONSTRUCTION
    assert amb.main_stage == "COMPLETED"


def test_classify_in_flight_no_start_is_missing(pg_session):
    """in-flight CONSTRUCTION 인데 명시 시공 시작 history 없음 → MISSING_START."""
    order = _order(pg_session, "CONSTRUCTION", history=[])
    amb = classify_order(order)
    assert isinstance(amb, AmbiguousConstructionAttempt)
    assert amb.reason == MISSING_START


def test_classify_malformed_fail_history_is_ambiguous(pg_session):
    """construction_fail_history 가 리스트 아님/ entry id 누락 → MALFORMED."""
    bad_type = _order(pg_session, "CONSTRUCTION", history=[_start_entry(1)],
                      fail_history={"oops": 1})
    assert classify_order(bad_type).reason == MALFORMED
    no_id = _order(pg_session, "CONSTRUCTION", history=[_start_entry(1)],
                   fail_history=[{"reason": "site_issue"}])
    assert classify_order(no_id).reason == MALFORMED


def test_classify_no_construction_is_excluded(pg_session):
    """시공 활동 없음(시작 0·재작업 0·main != CONSTRUCTION) → 대상 제외(None)."""
    order = _order(pg_session, "RECEIVED", history=[])
    assert classify_order(order) is None


# --------------------------------------------------------------------------- #
# dry-run / apply(승인 게이트) / verify
# --------------------------------------------------------------------------- #
def test_dry_run_writes_nothing(pg_session):
    """dry-run 은 발급 미리보기만 계산하고 DB 에 아무 것도 쓰지 않는다."""
    _order(pg_session, "CONSTRUCTION", history=[_start_entry(1)])
    _order(pg_session, "CONSTRUCTION", history=[_start_entry(1)])

    preview = dry_run(pg_session)
    assert preview.would_mint == 2
    assert preview.already_present == 0
    assert preview.ambiguous_skipped == 0
    # write 0: 아직 아무 attempt 도 생성되지 않았다.
    assert pg_session.query(OrderConstructionAttempt).count() == 0


def test_apply_without_approval_is_refused(pg_session):
    """apply 는 명시 승인 토큰 없이 호출하면 거부한다(command flag ON 금지)."""
    _order(pg_session, "CONSTRUCTION", history=[_start_entry(1)])

    with pytest.raises(ApprovalRequiredError):
        apply_safe_backfill(pg_session)              # 승인 없음
    with pytest.raises(ApprovalRequiredError):
        apply_safe_backfill(pg_session, approval="WRONG")  # 틀린 토큰
    # 거부됐으므로 발급 0.
    assert pg_session.query(OrderConstructionAttempt).count() == 0


def test_apply_mints_and_preserves_flat(pg_session):
    """승인 후 SAFE 주문에 attempt 발급, flat structured_data 는 무변경(보존)."""
    evidence = {"before": [1], "after": [2], "signature_att_id": 7}
    order = _order(pg_session, "CONSTRUCTION", history=[_start_entry(1)],
                   scheduled_date="2026-07-30", evidence=evidence)
    before = order.structured_data

    result = apply_safe_backfill(pg_session, approval=APPROVAL_TOKEN)
    pg_session.expire_all()

    assert result.attempts_minted == 1
    assert result.ambiguous_skipped == 0

    attempt = (
        pg_session.query(OrderConstructionAttempt)
        .filter_by(order_id=order.id).one()
    )
    assert attempt.status == "IN_PROGRESS" and attempt.is_current is True
    assert uuid.UUID(attempt.id)
    assert attempt.started_at is not None and attempt.started_by == "기사A"
    assert attempt.scheduled_date == "2026-07-30"
    assert attempt.evidence == evidence

    # flat 은 그대로 남아 있다(삭제/재작성 금지).
    reloaded = pg_session.get(Order, order.id).structured_data
    assert reloaded["workflow"] == before["workflow"]
    assert reloaded["construction"]["evidence"] == evidence


def test_apply_skips_ambiguous(pg_session):
    """ambiguous(복수 시작·재작업·직접 COMPLETED·누락) 주문은 attempt 를 발급하지 않는다(자동 매핑 0)."""
    _order(pg_session, "CONSTRUCTION", history=[_start_entry(1), _start_entry(2)])  # MULTIPLE_STARTS
    _order(pg_session, "COMPLETED", history=[_start_entry(1)])                       # PAST_CONSTRUCTION
    _order(pg_session, "CONSTRUCTION", history=[])                                   # MISSING_START

    result = apply_safe_backfill(pg_session, approval=APPROVAL_TOKEN)
    pg_session.expire_all()

    assert result.attempts_minted == 0
    assert result.ambiguous_skipped == 3
    assert pg_session.query(OrderConstructionAttempt).count() == 0


def test_verify_reports_100pct_after_apply(pg_session):
    """apply 후 모든 SAFE 주문이 current attempt 를 갖는다(verify ok, 100%)."""
    ids = [_order(pg_session, "CONSTRUCTION", history=[_start_entry(1)]).id for _ in range(3)]
    apply_safe_backfill(pg_session, approval=APPROVAL_TOKEN)
    pg_session.expire_all()

    v = verify(pg_session)
    assert v.ok is True
    assert v.safe_total == 3 and v.safe_covered == 3
    assert v.missing_order_ids == ()
    assert set(ids)  # 모든 주문이 대상이었음을 확인용으로 보존


def test_verify_incomplete_before_apply(pg_session):
    """apply 전에는 SAFE 주문이 current attempt 를 갖지 않아 verify 가 미완결이다."""
    _order(pg_session, "CONSTRUCTION", history=[_start_entry(1)])
    v = verify(pg_session)
    assert v.ok is False
    assert v.safe_total == 1 and v.safe_covered == 0


def test_manual_csv_lists_ambiguous_only(pg_session):
    """ambiguous 는 CSV 로 내보내진다(decision=MANUAL·approved 공란·자동 매핑 0)."""
    order = _order(pg_session, "CONSTRUCTION", history=[_start_entry(1), _start_entry(2)])
    csv_text = to_manual_csv(audit_construction_attempts(pg_session))
    assert ("order_id,main_stage,start_count,fail_count,legacy_scheduled_date,"
            "legacy_started_at,target_attempt_id,target_status,decision,reason,"
            "approved_by_user_id") in csv_text
    assert f"{order.id}," in csv_text
    assert f",MANUAL,{MULTIPLE_STARTS}," in csv_text


# --------------------------------------------------------------------------- #
# in-flight CONSTRUCTION current 100% 매핑
# --------------------------------------------------------------------------- #
def test_in_flight_maps_to_current_100pct(pg_session):
    """모든 in-flight CONSTRUCTION(단일 시작)이 current IN_PROGRESS attempt 로 100% 매핑된다."""
    ids = [_order(pg_session, "CONSTRUCTION", history=[_start_entry(1)]).id for _ in range(3)]
    audit = audit_construction_attempts(pg_session)
    assert audit.in_flight_ids == set(ids)
    assert audit.covers_all_in_flight() is True

    apply_safe_backfill(pg_session, approval=APPROVAL_TOKEN, audit=audit)
    pg_session.expire_all()
    for oid in ids:
        cur = (
            pg_session.query(OrderConstructionAttempt)
            .filter_by(order_id=oid, is_current=True).one()
        )
        assert cur.status == "IN_PROGRESS"


def test_coverage_incomplete_when_in_flight_ambiguous(pg_session):
    """in-flight 인데 복수 시작으로 ambiguous 면 coverage < 100%."""
    _order(pg_session, "CONSTRUCTION", history=[_start_entry(1)])                    # safe
    _order(pg_session, "CONSTRUCTION", history=[_start_entry(1), _start_entry(2)])   # ambiguous
    audit = audit_construction_attempts(pg_session)
    assert len(audit.in_flight_ids) == 2
    assert audit.covers_all_in_flight() is False


# --------------------------------------------------------------------------- #
# 멱등 / resume
# --------------------------------------------------------------------------- #
def test_apply_is_idempotent(pg_session):
    """재실행 시 이미 current attempt 가 있는 주문은 다시 발급하지 않는다."""
    _order(pg_session, "CONSTRUCTION", history=[_start_entry(1)])
    first = apply_safe_backfill(pg_session, approval=APPROVAL_TOKEN)
    assert first.attempts_minted == 1

    pg_session.expire_all()
    second = apply_safe_backfill(pg_session, approval=APPROVAL_TOKEN)
    assert second.attempts_minted == 0
    assert second.already_present == 1
    assert pg_session.query(OrderConstructionAttempt).count() == 1


# --------------------------------------------------------------------------- #
# enforcement 게이트
# --------------------------------------------------------------------------- #
def test_enforcement_gate_blocks_with_ambiguous(pg_session):
    """ambiguous 가 있으면 enforcement 게이트가 닫힌다."""
    _order(pg_session, "CONSTRUCTION", history=[_start_entry(1)])
    _order(pg_session, "CONSTRUCTION", history=[_start_entry(1), _start_entry(2)])   # ambiguous
    apply_safe_backfill(pg_session, approval=APPROVAL_TOKEN)
    pg_session.expire_all()
    assert can_enforce(pg_session) is False


def test_enforcement_gate_allows_when_clean(pg_session):
    """ambiguous 0 + 모든 in-flight current 100% 면 enforcement 가능."""
    _order(pg_session, "CONSTRUCTION", history=[_start_entry(1)])
    _order(pg_session, "RECEIVED", history=[])   # 시공 활동 없음: in-flight 아님
    apply_safe_backfill(pg_session, approval=APPROVAL_TOKEN)
    pg_session.expire_all()
    assert can_enforce(pg_session) is True


def test_enforcement_gate_blocks_before_backfill(pg_session):
    """in-flight 주문이 있는데 attempt 미발급이면(backfill 전) 게이트가 닫힌다."""
    _order(pg_session, "CONSTRUCTION", history=[_start_entry(1)])
    assert can_enforce(pg_session) is False


# --------------------------------------------------------------------------- #
# DB 제약: UUID unique · order binding · current 1개 · legacy 멱등
# --------------------------------------------------------------------------- #
def test_current_attempt_partial_unique(pg_session):
    """한 주문에 current attempt 는 최대 1개(partial unique) — 2번째 current 거부, 이력은 허용."""
    order = _order(pg_session, "CONSTRUCTION", history=[_start_entry(1)])
    apply_safe_backfill(pg_session, approval=APPROVAL_TOKEN)
    pg_session.expire_all()

    # 같은 주문에 2번째 current attempt 삽입 → partial unique 위반(DB 직격).
    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            pg_session.execute(OrderConstructionAttempt.__table__.insert().values(
                id=str(uuid.uuid4()), order_id=order.id, status="IN_PROGRESS",
                legacy_seq=99, is_current=True,
            ))

    # 종결된 attempt(is_current=False)은 같은 주문에 여러 개 허용(이력).
    with pg_session.begin_nested():
        pg_session.execute(OrderConstructionAttempt.__table__.insert().values(
            id=str(uuid.uuid4()), order_id=order.id, status="COMPLETED",
            legacy_seq=98, is_current=False,
        ))
    assert pg_session.query(OrderConstructionAttempt).filter_by(order_id=order.id).count() == 2


def test_legacy_seq_partial_unique(pg_session):
    """한 주문의 한 legacy_seq 에 attempt 는 최대 1개(중복 발급 방지·backfill 멱등)."""
    order = _order(pg_session, "CONSTRUCTION", history=[_start_entry(1)])
    apply_safe_backfill(pg_session, approval=APPROVAL_TOKEN)  # legacy_seq=0 발급
    pg_session.expire_all()

    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            pg_session.execute(OrderConstructionAttempt.__table__.insert().values(
                id=str(uuid.uuid4()), order_id=order.id, status="COMPLETED",
                legacy_seq=0, is_current=False,   # 같은 (order_id, legacy_seq)
            ))


def test_uuid_pk_global_unique(pg_session):
    """같은 UUID 재삽입은 PK 위반(DB-global unique)."""
    order = _order(pg_session, "CONSTRUCTION", history=[_start_entry(1)])
    apply_safe_backfill(pg_session, approval=APPROVAL_TOKEN)
    pg_session.expire_all()
    existing = pg_session.query(OrderConstructionAttempt).filter_by(order_id=order.id).one()

    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            pg_session.execute(OrderConstructionAttempt.__table__.insert().values(
                id=existing.id, order_id=order.id, status="COMPLETED",
                legacy_seq=5, is_current=False,
            ))
