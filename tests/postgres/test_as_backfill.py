"""AS-BACKFILL-00 PostgreSQL 계약 테스트 (PGTEST-00 lane).

AS 실행 UUID cycle registry(:class:`~models.OrderASCycle`)와 flat→cycle 매핑 backfill 을
실 PostgreSQL 로 검증한다:

* flat ``as_info`` (status/history 스냅샷) → cycle/transition/schedule/completion/
  classification safe map(유실 0·flat 잔존).
* current cycle 0/1(열린 entry 복수 → ambiguous).
* ambiguous(복수 열림·flat↔as_info 불일치·malformed)는 자동 매핑 0 → 수동 CSV.
* in-flight AS current **100% 매핑**(coverage)·backfill 멱등·resume·enforcement 게이트.
* UUID DB-global unique·order binding·current cycle partial-unique(1개)·legacy 멱등 unique.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip(conftest). 커밋 파일에 비밀번호 0
(dev DSN 은 env). 이 packet 은 아직 route/전이에 배선되지 않았다(AS-BACKFILL-00 경계 —
inferred stage rewrite·ambiguous cycle auto-select 금지) — 이 테스트가 하류(STATE-AS-01)가
의존할 계약을 정본으로 고정한다.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from foms.services.orders.audit_as_cycles import (
    MALFORMED,
    MULTIPLE_OPEN,
    STATUS_MISMATCH,
    ASCycleAudit,
    ASCyclePlan,
    AmbiguousASCycle,
    audit_as_cycles,
    classify_order,
    to_manual_csv,
)
from foms.services.orders.backfill_as_cycles import (
    apply_safe_backfill,
    can_enforce,
)
from models import Order, OrderASCycle


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _open_entry(as_id, *, scheduled=False):
    """열린(OPEN) as_info entry — as/start(+선택 as/schedule) 형태."""
    entry = {
        "id": as_id,
        "started_at": f"2026-07-2{as_id}T01:00:00",
        "started_by": "기사A",
        "reason": "파손",
        "description": "상판 흠집",
        "status": "OPEN",
        "visit_date": None,
        "completed_at": None,
    }
    if scheduled:
        entry["visit_date"] = "2026-08-01"
        entry["visit_time"] = "14:00"
        entry["scheduled_by"] = "기사A"
        entry["scheduled_at"] = f"2026-07-2{as_id}T02:00:00"
    return entry


def _completed_entry(as_id):
    """닫힌(COMPLETED) as_info entry — as/complete 형태."""
    entry = _open_entry(as_id)
    entry["status"] = "COMPLETED"
    entry["completed_at"] = f"2026-07-2{as_id}T05:00:00"
    entry["completed_by"] = "기사B"
    entry["completion_note"] = "교체 완료"
    return entry


def _sd(status, as_info):
    """order.status(flat AS 축 판정용) + as_info 리스트 structured_data."""
    return {"workflow": {"stage": status, "history": []}, "as_info": as_info}


def _order(session, status, as_info) -> Order:
    """ERP 주문 1건 생성(order.status = flat AS 축 원천)."""
    o = Order(
        received_date="2026-07-24", customer_name="홍길동", phone="010-0000-0000",
        address="서울", product="침대", is_erp_order=True, status=status,
        structured_data=_sd(status, as_info),
    )
    session.add(o)
    session.flush()
    return o


# --------------------------------------------------------------------------- #
# 분류: SAFE / ambiguous / 대상 제외 + safe map(5-facet)
# --------------------------------------------------------------------------- #
def test_classify_open_cycle_is_safe_current(pg_session):
    """flat AS(IN_PROGRESS)·열린 entry 1 → SAFE, current IN_PROGRESS cycle, 5-facet 스냅샷."""
    order = _order(pg_session, "AS", [_open_entry(1, scheduled=True)])
    plan = classify_order(order)
    assert isinstance(plan, ASCyclePlan)
    assert plan.order_id == order.id
    assert len(plan.cycles) == 1
    c = plan.cycles[0]
    assert c.legacy_as_id == 1
    assert c.status == "IN_PROGRESS"
    assert c.is_current is True
    assert c.started_at == "2026-07-21T01:00:00" and c.started_by == "기사A"  # transition
    assert c.reason == "파손" and c.description == "상판 흠집"                   # classification
    assert c.visit_date == "2026-08-01" and c.visit_time == "14:00"            # schedule
    assert c.completed_at is None                                              # completion(미완)
    assert plan.has_current() is True


def test_classify_completed_cycle_is_safe_history(pg_session):
    """flat 닫힘(CS)·닫힌 entry 1 → SAFE, current 0, COMPLETED 이력 cycle(completion 스냅샷)."""
    order = _order(pg_session, "CS", [_completed_entry(1)])
    plan = classify_order(order)
    assert isinstance(plan, ASCyclePlan)
    assert len(plan.cycles) == 1
    c = plan.cycles[0]
    assert c.status == "COMPLETED" and c.is_current is False
    assert c.completed_at == "2026-07-21T05:00:00" and c.completed_by == "기사B"
    assert c.completion_note == "교체 완료"
    assert plan.has_current() is False


def test_classify_multiple_completed_plus_open_is_safe(pg_session):
    """이력(닫힘 여러) + 열림 1 → SAFE, current 1, cycle 은 legacy_as_id 오름차순."""
    order = _order(pg_session, "AS",
                   [_completed_entry(1), _completed_entry(2), _open_entry(3)])
    plan = classify_order(order)
    assert isinstance(plan, ASCyclePlan)
    assert [c.legacy_as_id for c in plan.cycles] == [1, 2, 3]
    assert [c.is_current for c in plan.cycles] == [False, False, True]
    assert sum(c.is_current for c in plan.cycles) == 1  # current 0/1


def test_classify_multiple_open_is_ambiguous(pg_session):
    """열린 entry 복수 → current>1 자동 선택 금지 → MULTIPLE_OPEN."""
    order = _order(pg_session, "AS", [_open_entry(1), _open_entry(2)])
    amb = classify_order(order)
    assert isinstance(amb, AmbiguousASCycle)
    assert amb.reason == MULTIPLE_OPEN
    assert amb.open_count == 2 and amb.order_id == order.id


def test_classify_flat_open_no_entry_is_mismatch(pg_session):
    """flat AS_RECEIVED(register)인데 as_info 열린 entry 0 → STATUS_MISMATCH(registry 누락)."""
    order = _order(pg_session, "AS_RECEIVED", [])
    amb = classify_order(order)
    assert isinstance(amb, AmbiguousASCycle)
    assert amb.reason == STATUS_MISMATCH
    assert amb.as_axis == "RECEIVED"


def test_classify_flat_closed_but_open_entry_is_mismatch(pg_session):
    """flat 닫힘(CS)인데 as_info 열린 entry 잔존 → STATUS_MISMATCH(자동 조정 금지)."""
    order = _order(pg_session, "CS", [_open_entry(1)])
    amb = classify_order(order)
    assert isinstance(amb, AmbiguousASCycle)
    assert amb.reason == STATUS_MISMATCH


def test_classify_malformed_is_ambiguous(pg_session):
    """as_info 가 리스트 아님/ entry id 누락/알 수 없는 status → MALFORMED."""
    bad_type = _order(pg_session, "AS", {"oops": 1})       # as_info 가 dict
    assert classify_order(bad_type).reason == MALFORMED
    no_id = _order(pg_session, "AS", [{"status": "OPEN"}])  # id 누락
    assert classify_order(no_id).reason == MALFORMED
    bad_status = _order(pg_session, "AS", [{"id": 1, "status": "WEIRD"}])
    assert classify_order(bad_status).reason == MALFORMED


def test_classify_no_as_is_excluded(pg_session):
    """AS 활동 없음(as_info 없음 + flat NONE) → 대상 제외(None)."""
    order = _order(pg_session, "RECEIVED", None)
    order.structured_data = {"workflow": {"stage": "RECEIVED", "history": []}}
    pg_session.flush()
    assert classify_order(order) is None
    empty = _order(pg_session, "COMPLETED", [])  # 빈 as_info + flat 닫힘
    assert classify_order(empty) is None


# --------------------------------------------------------------------------- #
# backfill: SAFE 만 발급 + flat 보존 + 자동 매핑 0
# --------------------------------------------------------------------------- #
def test_backfill_mints_cycles_and_preserves_flat(pg_session):
    """SAFE 주문에 cycle 발급, flat structured_data 는 무변경(보존)."""
    order = _order(pg_session, "AS", [_completed_entry(1), _open_entry(2, scheduled=True)])
    before = order.structured_data

    result = apply_safe_backfill(pg_session)
    pg_session.expire_all()

    assert result.cycles_minted == 2
    assert result.ambiguous_skipped == 0

    cycles = (
        pg_session.query(OrderASCycle)
        .filter_by(order_id=order.id).order_by(OrderASCycle.legacy_as_id).all()
    )
    assert [c.status for c in cycles] == ["COMPLETED", "IN_PROGRESS"]
    assert [c.is_current for c in cycles] == [False, True]
    assert all(uuid.UUID(c.id) for c in cycles)
    cur = cycles[1]
    assert cur.started_at is not None and cur.visit_date == "2026-08-01"
    assert cur.reason == "파손"
    done = cycles[0]
    assert done.completed_at is not None and done.completion_note == "교체 완료"

    # flat 은 그대로 남아 있다(삭제/재작성 금지).
    reloaded = pg_session.get(Order, order.id).structured_data
    assert reloaded["as_info"] == before["as_info"]
    assert reloaded["workflow"] == before["workflow"]


def test_backfill_skips_ambiguous(pg_session):
    """ambiguous(복수 열림·불일치) 주문은 cycle 을 발급하지 않는다(자동 매핑 0)."""
    _order(pg_session, "AS", [_open_entry(1), _open_entry(2)])   # MULTIPLE_OPEN
    _order(pg_session, "AS_RECEIVED", [])                        # STATUS_MISMATCH

    result = apply_safe_backfill(pg_session)
    pg_session.expire_all()

    assert result.cycles_minted == 0
    assert result.ambiguous_skipped == 2
    assert pg_session.query(OrderASCycle).count() == 0


def test_manual_csv_lists_ambiguous_only(pg_session):
    """ambiguous 는 CSV 로 내보내진다(decision=MANUAL·approved 공란·자동 매핑 0)."""
    order = _order(pg_session, "AS", [_open_entry(1), _open_entry(2)])
    csv_text = to_manual_csv(audit_as_cycles(pg_session))
    assert ("order_id,as_axis,open_count,total_count,legacy_as_info_json,"
            "decision,reason,approved_by_user_id") in csv_text
    assert f"{order.id}," in csv_text
    assert f",MANUAL,{MULTIPLE_OPEN}," in csv_text


# --------------------------------------------------------------------------- #
# in-flight AS current 100% 매핑
# --------------------------------------------------------------------------- #
def test_in_flight_maps_to_current_100pct(pg_session):
    """모든 in-flight AS(열린 entry 1)가 current cycle 로 100% 매핑된다."""
    ids = [_order(pg_session, "AS", [_open_entry(1)]).id for _ in range(3)]
    audit = audit_as_cycles(pg_session)
    assert audit.in_flight_ids == set(ids)
    assert audit.covers_all_in_flight() is True

    apply_safe_backfill(pg_session, audit=audit)
    pg_session.expire_all()
    for oid in ids:
        cur = pg_session.query(OrderASCycle).filter_by(order_id=oid, is_current=True).one()
        assert cur.status == "IN_PROGRESS"


def test_coverage_incomplete_when_in_flight_ambiguous(pg_session):
    """in-flight 인데 열림 복수로 ambiguous 면 coverage < 100%."""
    _order(pg_session, "AS", [_open_entry(1)])                   # safe in-flight
    _order(pg_session, "AS", [_open_entry(1), _open_entry(2)])   # ambiguous in-flight
    audit = audit_as_cycles(pg_session)
    assert len(audit.in_flight_ids) == 2
    assert audit.covers_all_in_flight() is False


# --------------------------------------------------------------------------- #
# 멱등 / resume
# --------------------------------------------------------------------------- #
def test_backfill_is_idempotent(pg_session):
    """재실행 시 이미 발급된 (order_id, legacy_as_id) cycle 은 다시 발급하지 않는다."""
    _order(pg_session, "AS", [_completed_entry(1), _open_entry(2)])
    first = apply_safe_backfill(pg_session)
    assert first.cycles_minted == 2

    pg_session.expire_all()
    second = apply_safe_backfill(pg_session)
    assert second.cycles_minted == 0
    assert second.already_present == 2
    assert pg_session.query(OrderASCycle).count() == 2


def test_backfill_resumes_after_partial(pg_session):
    """부분 적용(한 주문만) 후 재실행이 남은 주문을 이어서 발급한다(중복 0)."""
    o1 = _order(pg_session, "AS", [_open_entry(1)])
    o2 = _order(pg_session, "AS", [_open_entry(1)])

    plan1 = classify_order(pg_session.get(Order, o1.id))
    partial = ASCycleAudit(safe=(plan1,), ambiguous=(), in_flight_ids=frozenset({o1.id}))
    apply_safe_backfill(pg_session, audit=partial)
    pg_session.expire_all()
    assert pg_session.query(OrderASCycle).filter_by(order_id=o1.id).count() == 1
    assert pg_session.query(OrderASCycle).filter_by(order_id=o2.id).count() == 0

    result = apply_safe_backfill(pg_session)
    pg_session.expire_all()
    assert result.cycles_minted == 1        # o2 만 신규
    assert result.already_present == 1       # o1 은 이미 있음
    assert pg_session.query(OrderASCycle).filter_by(order_id=o2.id).count() == 1


# --------------------------------------------------------------------------- #
# enforcement 게이트
# --------------------------------------------------------------------------- #
def test_enforcement_gate_blocks_with_ambiguous(pg_session):
    """ambiguous 가 있으면 enforcement 게이트가 닫힌다."""
    _order(pg_session, "AS", [_open_entry(1)])
    _order(pg_session, "AS", [_open_entry(1), _open_entry(2)])   # ambiguous
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    assert can_enforce(pg_session) is False


def test_enforcement_gate_allows_when_clean(pg_session):
    """ambiguous 0 + 모든 in-flight current 100% 면 enforcement 가능."""
    _order(pg_session, "AS", [_open_entry(1)])
    _order(pg_session, "CS", [_completed_entry(1)])   # 닫힘: in-flight 아님
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    assert can_enforce(pg_session) is True


def test_enforcement_gate_blocks_before_backfill(pg_session):
    """in-flight 주문이 있는데 cycle 미발급이면(backfill 전) 게이트가 닫힌다."""
    _order(pg_session, "AS", [_open_entry(1)])
    assert can_enforce(pg_session) is False


# --------------------------------------------------------------------------- #
# DB 제약: UUID unique · order binding · current 1개 · legacy 멱등
# --------------------------------------------------------------------------- #
def test_current_cycle_partial_unique(pg_session):
    """한 주문에 current cycle 은 최대 1개(partial unique) — 2번째 current 는 거부, 이력은 허용."""
    order = _order(pg_session, "AS", [_open_entry(1)])
    apply_safe_backfill(pg_session)
    pg_session.expire_all()

    # 같은 주문에 2번째 current cycle 삽입 → partial unique 위반(DB 직격).
    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            pg_session.execute(OrderASCycle.__table__.insert().values(
                id=str(uuid.uuid4()), order_id=order.id, status="IN_PROGRESS",
                legacy_as_id=99, is_current=True,
            ))

    # 종결된 cycle(is_current=False)은 같은 주문에 여러 개 허용(이력).
    with pg_session.begin_nested():
        pg_session.execute(OrderASCycle.__table__.insert().values(
            id=str(uuid.uuid4()), order_id=order.id, status="COMPLETED",
            legacy_as_id=98, is_current=False,
        ))
    assert pg_session.query(OrderASCycle).filter_by(order_id=order.id).count() == 2


def test_legacy_id_partial_unique(pg_session):
    """한 주문의 한 legacy_as_id 에 cycle 은 최대 1개(중복 발급 방지·backfill 멱등)."""
    order = _order(pg_session, "AS", [_open_entry(1)])
    apply_safe_backfill(pg_session)
    pg_session.expire_all()

    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            pg_session.execute(OrderASCycle.__table__.insert().values(
                id=str(uuid.uuid4()), order_id=order.id, status="COMPLETED",
                legacy_as_id=1, is_current=False,   # 같은 (order_id, legacy_as_id)
            ))


def test_uuid_pk_global_unique(pg_session):
    """같은 UUID 재삽입은 PK 위반(DB-global unique)."""
    order = _order(pg_session, "AS", [_open_entry(1)])
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    existing = pg_session.query(OrderASCycle).filter_by(order_id=order.id).one()

    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            pg_session.execute(OrderASCycle.__table__.insert().values(
                id=existing.id, order_id=order.id, status="COMPLETED",
                legacy_as_id=2, is_current=False,
            ))
