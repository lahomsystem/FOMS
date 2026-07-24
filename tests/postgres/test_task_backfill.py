"""TASK-BACKFILL-00 PostgreSQL 계약 테스트 (PGTEST-00 lane).

flat :class:`~models.OrderTask` → UUID identity expand/audit/backfill 을 실 PostgreSQL 로
검증한다:

* 6축(orphan/status/date/team/user/auto_key) audit 분리 분류.
* **MEASURE→SALES safe mapping**(team-clean)·auto collisions 0.
* SAFE 만 UUID/version=1/LEGACY provenance seed, ambiguous quarantine(자동 매핑 0·
  active enforcement 금지)·creator 추정 0.
* coverage 100%·backfill 멱등·resume·enforcement 게이트.
* ``task_uuid`` DB-global partial-unique(NULL 다중 허용)·flat 컬럼 무변경(expand).

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip(conftest). 커밋 파일에 비밀번호 0
(dev DSN 은 env). 이 packet 은 아직 route/전이에 배선되지 않았다(TASK-BACKFILL-00 경계 —
전이/collision enforcement 는 하류 TASK-01) — 이 테스트가 하류가 의존할 계약을 고정한다.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from foms.services.orders.audit_order_tasks import (
    AUTO_COLLISION,
    BAD_DATE,
    BAD_STATUS,
    BAD_TEAM,
    BAD_USER,
    ORPHAN,
    AmbiguousTask,
    audit_order_tasks,
    to_manual_csv,
)
from foms.services.orders.backfill_order_tasks import (
    PROVENANCE_LEGACY,
    apply_safe_backfill,
    can_enforce,
)
from models import Order, OrderTask, User


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _order(session, *, deleted=False) -> Order:
    """ERP 주문 1건 생성(deleted=True 면 soft-delete → orphan 원천)."""
    o = Order(
        received_date="2026-07-24", customer_name="홍길동", phone="010-0000-0000",
        address="서울", product="침대", is_erp_order=True, status="RECEIVED",
        structured_data={"workflow": {"stage": "RECEIVED"}},
        deleted_at=("2026-07-25T00:00:00" if deleted else None),
    )
    session.add(o)
    session.flush()
    return o


def _user(session, *, active=True) -> User:
    """User 1건 생성(active=False 면 비활성 → BAD_USER 원천)."""
    u = User(username=f"qa_{uuid.uuid4().hex[:8]}", password="x", name="QA",
             role="STAFF", is_active=active)
    session.add(u)
    session.flush()
    return u


def _task(session, order, *, status="OPEN", owner_team=None, owner_user_id=None,
          due_date=None, auto_key=None, title="팔로업") -> OrderTask:
    """order_tasks 1건 생성(meta.auto_key 옵션)."""
    meta = {"auto_key": auto_key} if auto_key else None
    t = OrderTask(
        order_id=order.id, title=title, status=status, owner_team=owner_team,
        owner_user_id=owner_user_id, due_date=due_date, meta=meta,
    )
    session.add(t)
    session.flush()
    return t


def _ambiguous_by_id(session):
    """audit 결과를 task_id → AmbiguousTask 로 인덱싱."""
    audit = audit_order_tasks(session)
    return audit, {a.task_id: a for a in audit.ambiguous}


# --------------------------------------------------------------------------- #
# 분류: SAFE / 6축 ambiguous
# --------------------------------------------------------------------------- #
def test_clean_task_is_safe(pg_session):
    """유효 status/date/team/user·활성 주문·auto_key 없음 → SAFE."""
    o = _order(pg_session)
    u = _user(pg_session)
    t = _task(pg_session, o, status="OPEN", owner_team="CS",
              owner_user_id=u.id, due_date="2026-08-01")
    audit = audit_order_tasks(pg_session)
    assert [s.task_id for s in audit.safe] == [t.id]
    assert audit.ambiguous == ()


def test_measure_team_maps_to_sales_is_safe(pg_session):
    """owner_team=MEASURE(legacy pseudo-team)는 SALES 로 정규화되어 team-clean → SAFE."""
    o = _order(pg_session)
    t_upper = _task(pg_session, o, owner_team="MEASURE")
    t_lower = _task(pg_session, o, owner_team="measure")   # trim/upper 도 정규화
    audit = audit_order_tasks(pg_session)
    assert {t_upper.id, t_lower.id} <= audit.safe_ids()
    assert audit.ambiguous == ()


def test_bad_team_is_ambiguous(pg_session):
    """canonical 이 아닌 owner_team → BAD_TEAM(자동 보정 금지)."""
    o = _order(pg_session)
    t = _task(pg_session, o, owner_team="GARBAGE")
    _audit, amb = _ambiguous_by_id(pg_session)
    assert amb[t.id].reasons == (BAD_TEAM,)


def test_bad_status_is_ambiguous(pg_session):
    """알 수 없는 status → BAD_STATUS."""
    o = _order(pg_session)
    t = _task(pg_session, o, status="WEIRD")
    _audit, amb = _ambiguous_by_id(pg_session)
    assert amb[t.id].reasons == (BAD_STATUS,)


def test_bad_date_is_ambiguous(pg_session):
    """파싱 불가 due_date → BAD_DATE. None/유효 ISO 는 clean."""
    o = _order(pg_session)
    bad = _task(pg_session, o, due_date="곧")
    bad2 = _task(pg_session, o, due_date="2026-13-40")
    good = _task(pg_session, o, due_date=None)
    _audit, amb = _ambiguous_by_id(pg_session)
    assert amb[bad.id].reasons == (BAD_DATE,)
    assert amb[bad2.id].reasons == (BAD_DATE,)
    assert good.id not in amb


def test_bad_user_is_ambiguous(pg_session):
    """비활성(is_active=False) User 소유 → BAD_USER(존재/활성 검증만·creator 추정 금지)."""
    o = _order(pg_session)
    inactive = _user(pg_session, active=False)
    t = _task(pg_session, o, owner_user_id=inactive.id)
    _audit, amb = _ambiguous_by_id(pg_session)
    assert amb[t.id].reasons == (BAD_USER,)


def test_orphan_on_soft_deleted_order_is_ambiguous(pg_session):
    """soft-delete 된 주문의 task → ORPHAN."""
    o = _order(pg_session, deleted=True)
    t = _task(pg_session, o)
    _audit, amb = _ambiguous_by_id(pg_session)
    assert amb[t.id].reasons == (ORPHAN,)


def test_multiple_reasons_are_all_recorded(pg_session):
    """여러 축이 동시에 깨지면 사유가 모두(정렬·중복제거) 기록된다(분리 분류)."""
    o = _order(pg_session)
    t = _task(pg_session, o, status="WEIRD", owner_team="NOPE", due_date="bad")
    _audit, amb = _ambiguous_by_id(pg_session)
    assert amb[t.id].reasons == tuple(sorted((BAD_STATUS, BAD_TEAM, BAD_DATE)))


# --------------------------------------------------------------------------- #
# auto_key collisions
# --------------------------------------------------------------------------- #
def test_active_auto_key_collision_is_ambiguous(pg_session):
    """같은 (order_id, auto_key)의 활성 task 2개 → 둘 다 AUTO_COLLISION."""
    o = _order(pg_session)
    a = _task(pg_session, o, status="OPEN", auto_key="AUTO_URGENT")
    b = _task(pg_session, o, status="IN_PROGRESS", auto_key="AUTO_URGENT")
    _audit, amb = _ambiguous_by_id(pg_session)
    assert amb[a.id].reasons == (AUTO_COLLISION,)
    assert amb[b.id].reasons == (AUTO_COLLISION,)


def test_terminal_duplicate_auto_key_is_not_collision(pg_session):
    """활성 1 + 종결 1(같은 auto_key)은 활성 중복이 아니므로 collision 아님 → 둘 다 SAFE."""
    o = _order(pg_session)
    live = _task(pg_session, o, status="OPEN", auto_key="AUTO_MEASURE_D4")
    done = _task(pg_session, o, status="DONE", auto_key="AUTO_MEASURE_D4")
    audit = audit_order_tasks(pg_session)
    assert {live.id, done.id} <= audit.safe_ids()
    assert audit.ambiguous == ()


def test_same_auto_key_different_orders_is_not_collision(pg_session):
    """다른 주문의 같은 auto_key 는 collision 이 아니다(주문 스코프)."""
    o1, o2 = _order(pg_session), _order(pg_session)
    t1 = _task(pg_session, o1, status="OPEN", auto_key="AUTO_URGENT")
    t2 = _task(pg_session, o2, status="OPEN", auto_key="AUTO_URGENT")
    audit = audit_order_tasks(pg_session)
    assert {t1.id, t2.id} <= audit.safe_ids()


# --------------------------------------------------------------------------- #
# backfill: SAFE 만 seed + flat 보존 + 자동 매핑 0
# --------------------------------------------------------------------------- #
def test_backfill_seeds_safe_only_and_preserves_flat(pg_session):
    """SAFE 만 UUID/version=1/LEGACY seed, ambiguous 는 NULL(quarantine), flat 무변경."""
    o = _order(pg_session)
    safe = _task(pg_session, o, owner_team="MEASURE", due_date="2026-08-01")
    bad = _task(pg_session, o, status="WEIRD")
    before_team, before_status = safe.owner_team, bad.status

    result = apply_safe_backfill(pg_session)
    pg_session.expire_all()

    assert result.tasks_seeded == 1
    assert result.ambiguous_skipped == 1

    safe_row = pg_session.get(OrderTask, safe.id)
    assert uuid.UUID(safe_row.task_uuid)          # 유효 UUID
    assert safe_row.version == 1
    assert safe_row.provenance == PROVENANCE_LEGACY
    # flat 컬럼은 재작성되지 않는다(MEASURE 를 SALES 로 덮지 않음 — expand 단계).
    assert safe_row.owner_team == before_team == "MEASURE"

    bad_row = pg_session.get(OrderTask, bad.id)    # ambiguous 는 손대지 않음
    assert bad_row.task_uuid is None
    assert bad_row.version is None and bad_row.provenance is None
    assert bad_row.status == before_status == "WEIRD"


def test_backfill_does_not_infer_creator(pg_session):
    """provenance 는 항상 LEGACY, owner_user_id 는 seed 로 채워지지 않는다(creator 추정 0)."""
    o = _order(pg_session)
    t = _task(pg_session, o, owner_user_id=None)
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    row = pg_session.get(OrderTask, t.id)
    assert row.provenance == PROVENANCE_LEGACY
    assert row.owner_user_id is None               # 추정/보정 없음


def test_backfill_coverage_100pct(pg_session):
    """모든 SAFE task 가 UUID 를 받는다(coverage 100%)."""
    o = _order(pg_session)
    safe_ids = [_task(pg_session, o, title=f"t{i}").id for i in range(5)]
    _task(pg_session, o, status="WEIRD")           # ambiguous 1건(제외)
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    seeded = (
        pg_session.query(OrderTask.id)
        .filter(OrderTask.id.in_(safe_ids), OrderTask.task_uuid.isnot(None))
        .count()
    )
    assert seeded == len(safe_ids)


def test_backfill_is_idempotent(pg_session):
    """재실행 시 이미 UUID 가 있는 SAFE task 는 다시 seed 하지 않는다."""
    o = _order(pg_session)
    _task(pg_session, o)
    _task(pg_session, o)
    first = apply_safe_backfill(pg_session)
    assert first.tasks_seeded == 2

    pg_session.expire_all()
    second = apply_safe_backfill(pg_session)
    assert second.tasks_seeded == 0
    assert second.already_present == 2


def test_backfill_resumes_after_partial(pg_session):
    """부분 seed(한 task 만) 후 재실행이 남은 SAFE task 를 이어서 seed 한다(중복 0)."""
    from foms.services.orders.audit_order_tasks import SafeTask, TaskAudit

    o = _order(pg_session)
    t1 = _task(pg_session, o)
    t2 = _task(pg_session, o)

    partial = TaskAudit(safe=(SafeTask(task_id=t1.id, order_id=o.id),),
                        ambiguous=(), active_ids=frozenset({t1.id}))
    apply_safe_backfill(pg_session, audit=partial)
    pg_session.expire_all()
    assert pg_session.get(OrderTask, t1.id).task_uuid is not None
    assert pg_session.get(OrderTask, t2.id).task_uuid is None

    result = apply_safe_backfill(pg_session)       # 전체 audit → t2 만 신규
    pg_session.expire_all()
    assert result.tasks_seeded == 1
    assert result.already_present == 1
    assert pg_session.get(OrderTask, t2.id).task_uuid is not None


def test_manual_csv_lists_ambiguous_only(pg_session):
    """ambiguous 는 CSV 로 내보내진다(decision=MANUAL·approved 공란·자동 매핑 0)."""
    o = _order(pg_session)
    _task(pg_session, o)                            # SAFE(CSV 미포함)
    bad = _task(pg_session, o, status="WEIRD", owner_team="NOPE")
    csv_text = to_manual_csv(audit_order_tasks(pg_session))
    assert ("task_id,order_id,status,owner_team,owner_user_id,due_date,auto_key,"
            "reasons,decision,approved_by_user_id") in csv_text
    assert f"\n{bad.id},{o.id}," in csv_text
    assert f"{BAD_STATUS}|{BAD_TEAM}" in csv_text
    assert ",MANUAL," in csv_text


# --------------------------------------------------------------------------- #
# enforcement 게이트
# --------------------------------------------------------------------------- #
def test_enforcement_blocks_with_ambiguous(pg_session):
    """ambiguous 가 있으면 게이트가 닫힌다."""
    o = _order(pg_session)
    _task(pg_session, o)
    _task(pg_session, o, status="WEIRD")           # ambiguous
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    assert can_enforce(pg_session) is False


def test_enforcement_blocks_before_backfill(pg_session):
    """활성 task 가 있는데 UUID 미발급(backfill 전)이면 게이트가 닫힌다."""
    o = _order(pg_session)
    _task(pg_session, o, status="OPEN")
    assert can_enforce(pg_session) is False


def test_enforcement_allows_when_clean(pg_session):
    """ambiguous 0 + 모든 활성 task UUID 보유면 enforcement 가능."""
    o = _order(pg_session)
    _task(pg_session, o, status="OPEN")
    _task(pg_session, o, status="DONE")            # 종결: 활성 아님
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    assert can_enforce(pg_session) is True


# --------------------------------------------------------------------------- #
# DB 제약: task_uuid partial-unique(NULL 다중 허용)
# --------------------------------------------------------------------------- #
def test_task_uuid_partial_unique_global(pg_session):
    """발급된 task_uuid 는 전 DB 유일 — 같은 UUID 재사용은 거부."""
    o = _order(pg_session)
    a = _task(pg_session, o)
    b = _task(pg_session, o)
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    a_uuid = pg_session.get(OrderTask, a.id).task_uuid

    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            pg_session.execute(
                OrderTask.__table__.update()
                .where(OrderTask.__table__.c.id == b.id)
                .values(task_uuid=a_uuid)          # 중복 UUID → partial-unique 위반
            )


def test_task_uuid_null_allowed_for_many_ambiguous(pg_session):
    """ambiguous 다수는 task_uuid=NULL 로 공존한다(partial-unique 가 NULL 을 막지 않음)."""
    o = _order(pg_session)
    _task(pg_session, o, status="WEIRD")
    _task(pg_session, o, status="WEIRD")
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    nulls = (
        pg_session.query(OrderTask.id)
        .filter(OrderTask.order_id == o.id, OrderTask.task_uuid.is_(None))
        .count()
    )
    assert nulls == 2
