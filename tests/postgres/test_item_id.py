"""ITEM-ID-00 PostgreSQL 계약 테스트 (PGTEST-00 lane).

주문 아이템 UUID identity registry(:class:`~models.OrderItemIdentity`) 와 첨부/일정의
안정 ``item_id`` 결합을 실 PostgreSQL 로 검증한다:

* UUID **DB-global unique** · **order binding** · **immutable/no-reuse**(tombstone 후 같은
  UUID 재삽입/같은 슬롯 2중 활성 거부).
* attachment/schedule **exact backfill(safe 만)** · **ambiguous 자동 매핑 0**(수동 CSV 분류).
* **enforcement 게이트**: ambiguous 존재 시 NOT NULL 미적용, 0건 + 전 행 링크 후 적용 가능.
* read-model(item_id 로 조회) · date-sync rebuild 가 item_id 를 registry 에서 재채움(유실 0).

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip(conftest). 커밋 파일에 비밀번호 0
(dev DSN 은 env). 이 packet 은 아직 route/AUTH 에 배선되지 않았다(ITEM-ID-00 경계) — 이
테스트가 하류(DATA-01·WIZ-01·UPLOAD-02)가 의존할 계약을 정본으로 고정한다.
"""
from __future__ import annotations

import copy
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified

from foms.services.orders.audit_order_item_identities import (
    NEGATIVE_INDEX,
    OUT_OF_RANGE,
    ItemIdentityAudit,
    audit_item_identities,
    to_manual_csv,
)
from foms.services.orders.backfill_order_item_identities import (
    apply_safe_backfill,
    can_enforce_not_null,
)
from foms.services.orders.item_identity import (
    ItemIdentityError,
    attachments_for_item,
    get_or_create_identity,
    resolve_active_item_id,
    retire_identity,
    schedule_dates_for_item,
)
from models import Order, OrderAttachment, OrderItemIdentity, OrderScheduleDate


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _order(session, items=None) -> Order:
    """ERP 주문 1건 생성(structured_data.items 로 아이템 수 지정)."""
    o = Order(
        received_date="2026-07-24", customer_name="홍길동", phone="010-0000-0000",
        address="서울", product="침대", is_erp_order=True,
        structured_data={"items": items if items is not None else []},
    )
    session.add(o)
    session.flush()
    return o


def _attach(session, order, item_index, *, item_id=None, category="measurement") -> OrderAttachment:
    a = OrderAttachment(
        order_id=order.id, filename="f.jpg", file_type="image", category=category,
        item_index=item_index, item_id=item_id, file_size=1, storage_key="k",
    )
    session.add(a)
    session.flush()
    return a


def _schedule(session, order, item_index, *, item_id=None, kind="construction",
              date="2026-08-01", source="beta_item") -> OrderScheduleDate:
    """일정 row 를 직접 추가(order 를 dirty 화하지 않아 date-sync 리스너가 덮지 않음)."""
    s = OrderScheduleDate(
        order_id=order.id, kind=kind, date=date, source=source,
        item_index=item_index, item_id=item_id,
    )
    session.add(s)
    session.flush()
    return s


# --------------------------------------------------------------------------- #
# UUID unique / order binding / immutable-no-reuse
# --------------------------------------------------------------------------- #
def test_uuid_global_unique_and_order_binding(pg_session):
    """서로 다른 identity 는 UUID 가 다르고, 같은 UUID 재삽입은 PK 위반이다."""
    order_a = _order(pg_session, items=[{}])
    order_b = _order(pg_session, items=[{}])
    id_a = get_or_create_identity(pg_session, order_a.id, 0)
    id_b = get_or_create_identity(pg_session, order_b.id, 0)

    assert id_a.id != id_b.id                 # DB-global unique UUID
    assert id_a.order_id == order_a.id         # order binding
    assert id_b.order_id == order_b.id
    assert uuid.UUID(id_a.id)                  # canonical UUID 문자열

    # 같은 UUID 를 다른 주문/슬롯으로 재삽입 → PK 위반(전역 유일). DB 제약을 직접 치도록
    # Core insert 로 삽입한다(ORM identity-map 우회).
    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            pg_session.execute(OrderItemIdentity.__table__.insert().values(
                id=id_a.id, order_id=order_b.id, item_index=9, is_active=True,
            ))


def test_get_or_create_is_idempotent(pg_session):
    """같은 (order, index) 슬롯에 대한 반복 호출은 같은 활성 identity 를 돌려준다."""
    order = _order(pg_session, items=[{}, {}])
    first = get_or_create_identity(pg_session, order.id, 1)
    again = get_or_create_identity(pg_session, order.id, 1)
    assert first.id == again.id


def test_immutable_no_reuse_after_tombstone(pg_session):
    """tombstone 후: 같은 UUID 재삽입 거부, 같은 슬롯 2중 활성 거부, 슬롯은 새 UUID 로 재발급."""
    order = _order(pg_session, items=[{}])
    original = get_or_create_identity(pg_session, order.id, 0)
    original_uuid = original.id

    retired = retire_identity(pg_session, original_uuid)
    assert retired.is_active is False
    assert retired.retired_at is not None

    # 같은 슬롯 재발급 → 새 UUID(은퇴 UUID 재사용 금지).
    reissued = get_or_create_identity(pg_session, order.id, 0)
    assert reissued.id != original_uuid
    assert reissued.is_active is True

    # 은퇴한 UUID 를 다시 활성으로 삽입 시도 → PK 위반(no-reuse). Core insert 로 DB 직격.
    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            pg_session.execute(OrderItemIdentity.__table__.insert().values(
                id=original_uuid, order_id=order.id, item_index=0, is_active=True,
            ))

    # 같은 슬롯에 2번째 활성 identity 삽입 → partial unique 위반(새 UUID, DB 직격).
    with pytest.raises(IntegrityError):
        with pg_session.begin_nested():
            pg_session.execute(OrderItemIdentity.__table__.insert().values(
                id=str(uuid.uuid4()), order_id=order.id, item_index=0, is_active=True,
            ))


def test_get_or_create_rejects_negative_index(pg_session):
    """음수 인덱스는 유효 슬롯이 아니므로 발급을 거부한다."""
    order = _order(pg_session, items=[{}])
    with pytest.raises(ItemIdentityError):
        get_or_create_identity(pg_session, order.id, -1)


# --------------------------------------------------------------------------- #
# audit: safe / ambiguous 분류 + 자동 매핑 0
# --------------------------------------------------------------------------- #
def test_audit_classifies_safe_and_ambiguous(pg_session):
    """in-range=safe, out-of-range/음수=ambiguous, 공통(None)=대상 제외."""
    order = _order(pg_session, items=[{}, {}])  # item_count = 2 → 유효 인덱스 {0,1}
    _attach(pg_session, order, 0)               # safe
    _attach(pg_session, order, 1)               # safe
    out = _attach(pg_session, order, 5)         # ambiguous OUT_OF_RANGE
    neg = _attach(pg_session, order, -1)        # ambiguous NEGATIVE_INDEX
    _attach(pg_session, order, None)            # 공통 → 분류 대상 아님

    audit = audit_item_identities(pg_session)
    assert (order.id, 0) in audit.safe
    assert (order.id, 1) in audit.safe

    reasons = {(a.ref_id, a.reason) for a in audit.ambiguous}
    assert (out.id, OUT_OF_RANGE) in reasons
    assert (neg.id, NEGATIVE_INDEX) in reasons
    # 공통(None)/safe 는 ambiguous 에 없다.
    assert all(a.item_index is not None for a in audit.ambiguous)
    assert (order.id, 5) not in audit.safe
    assert (order.id, -1) not in audit.safe


def test_manual_csv_contains_ambiguous(pg_session):
    """ambiguous 결합은 수동 매핑 CSV 로 내보내진다(header + 행)."""
    order = _order(pg_session, items=[{}])       # item_count = 1
    out = _attach(pg_session, order, 3)          # OUT_OF_RANGE

    csv_text = to_manual_csv(audit_item_identities(pg_session))
    assert "order_id,item_index,ref_kind,ref_id,reason,item_count" in csv_text
    assert f"{order.id},3,attachment,{out.id},{OUT_OF_RANGE},1" in csv_text


# --------------------------------------------------------------------------- #
# backfill: safe 만 정확 매핑 + ambiguous 무접근(자동 매핑 0)
# --------------------------------------------------------------------------- #
def test_apply_safe_backfill_links_only_safe(pg_session):
    """safe 슬롯만 UUID 발급/링크, ambiguous·공통은 item_id NULL 유지(자동 매핑 0)."""
    order = _order(pg_session, items=[{}, {}])
    a0 = _attach(pg_session, order, 0)
    a1 = _attach(pg_session, order, 1)
    a_out = _attach(pg_session, order, 7)     # ambiguous
    a_common = _attach(pg_session, order, None)
    s0 = _schedule(pg_session, order, 0)      # safe 일정
    s_out = _schedule(pg_session, order, 9)   # ambiguous 일정

    result = apply_safe_backfill(pg_session)
    pg_session.expire_all()

    assert result.identities_minted == 2       # (order,0),(order,1)
    assert result.attachments_linked == 2      # a0,a1
    assert result.schedule_dates_linked == 1   # s0
    assert result.ambiguous_skipped == 2       # a_out, s_out

    id0 = resolve_active_item_id(pg_session, order.id, 0)
    id1 = resolve_active_item_id(pg_session, order.id, 1)
    assert id0 and id1 and id0 != id1

    # safe 행은 정확히 슬롯 UUID 로 링크.
    assert pg_session.get(OrderAttachment, a0.id).item_id == id0
    assert pg_session.get(OrderAttachment, a1.id).item_id == id1
    assert pg_session.get(OrderScheduleDate, s0.id).item_id == id0

    # ambiguous/공통 은 절대 링크되지 않는다(자동 매핑 0).
    assert pg_session.get(OrderAttachment, a_out.id).item_id is None
    assert pg_session.get(OrderAttachment, a_common.id).item_id is None
    assert pg_session.get(OrderScheduleDate, s_out.id).item_id is None


def test_backfill_is_idempotent(pg_session):
    """재실행 시 이미 링크된 행은 다시 발급/링크하지 않는다."""
    order = _order(pg_session, items=[{}])
    _attach(pg_session, order, 0)

    first = apply_safe_backfill(pg_session)
    assert first.identities_minted == 1
    assert first.attachments_linked == 1

    pg_session.expire_all()
    second = apply_safe_backfill(pg_session)
    assert second.identities_minted == 0
    assert second.attachments_linked == 0


def test_backfill_resumes_after_partial_batch(pg_session):
    """부분 배치(한 슬롯만) 적용 후, 재실행이 남은 슬롯을 이어서 링크한다(재발급/중복 0).

    runs.py lease/checkpoint 없이 자원 idempotency 로 resume 을 보장하는지 검증한다.
    """
    order = _order(pg_session, items=[{}, {}])
    a0 = _attach(pg_session, order, 0)
    a1 = _attach(pg_session, order, 1)

    # 첫 배치가 (order,0)만 처리했다고 가정(부분 진행).
    partial = ItemIdentityAudit(safe=frozenset({(order.id, 0)}), ambiguous=())
    apply_safe_backfill(pg_session, audit=partial)
    pg_session.expire_all()
    id0 = resolve_active_item_id(pg_session, order.id, 0)
    assert pg_session.get(OrderAttachment, a0.id).item_id == id0
    assert pg_session.get(OrderAttachment, a1.id).item_id is None  # 아직 미처리

    # 전체 재실행 → 남은 (order,1)만 이어서 링크, (order,0)은 재발급/중복 0.
    result = apply_safe_backfill(pg_session)
    pg_session.expire_all()
    assert result.identities_minted == 1        # (order,1)만 신규
    assert result.attachments_linked == 1       # a1만
    assert resolve_active_item_id(pg_session, order.id, 0) == id0  # (order,0) 불변
    assert pg_session.get(OrderAttachment, a1.id).item_id is not None


# --------------------------------------------------------------------------- #
# enforcement 게이트
# --------------------------------------------------------------------------- #
def test_enforcement_gate_blocks_with_ambiguous(pg_session):
    """ambiguous 결합이 있으면 NOT NULL enforcement 를 걸 수 없다."""
    order = _order(pg_session, items=[{}, {}])
    _attach(pg_session, order, 0)
    _attach(pg_session, order, 8)   # ambiguous
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    assert can_enforce_not_null(pg_session) is False


def test_enforcement_gate_allows_when_clean(pg_session):
    """ambiguous 0건 + 전 아이템-스코프 행 링크 완료면 enforcement 가능."""
    order = _order(pg_session, items=[{}, {}])
    _attach(pg_session, order, 0)
    _attach(pg_session, order, 1)
    _attach(pg_session, order, None)   # 공통은 item_index None → enforcement 대상 아님
    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    assert can_enforce_not_null(pg_session) is True


# --------------------------------------------------------------------------- #
# read-model
# --------------------------------------------------------------------------- #
def test_read_model_by_item_id(pg_session):
    """item_id UUID 로 첨부/일정을 조회한다(위치 인덱스 아님)."""
    order = _order(pg_session, items=[{}])
    identity = get_or_create_identity(pg_session, order.id, 0)
    a1 = _attach(pg_session, order, 0, item_id=identity.id)
    a2 = _attach(pg_session, order, 0, item_id=identity.id)
    _attach(pg_session, order, None)                       # 공통(링크 안 됨)
    s1 = _schedule(pg_session, order, 0, item_id=identity.id)

    att_ids = {a.id for a in attachments_for_item(pg_session, identity.id)}
    assert att_ids == {a1.id, a2.id}
    sch_ids = {s.id for s in schedule_dates_for_item(pg_session, identity.id)}
    assert sch_ids == {s1.id}


# --------------------------------------------------------------------------- #
# date-sync 통합: rebuild 시 item_id 유실 0
# --------------------------------------------------------------------------- #
def test_date_sync_preserves_item_id_on_rebuild(pg_session):
    """일정 rebuild(날짜 변경) 후에도 item_id 가 registry 에서 재채워진다."""
    order = _order(pg_session, items=[{"construction_date": "2026-08-01"}])
    # 리스너가 item 날짜로 일정 row(construction, item_index=0)를 생성.
    sched = (
        pg_session.query(OrderScheduleDate)
        .filter_by(order_id=order.id, kind="construction", item_index=0)
        .one()
    )
    assert sched.item_id is None

    apply_safe_backfill(pg_session)
    pg_session.expire_all()
    linked_uuid = resolve_active_item_id(pg_session, order.id, 0)
    assert linked_uuid is not None

    # 아이템 날짜 변경 → 리스너가 일정 row 를 rebuild(교체).
    sd = copy.deepcopy(order.structured_data)
    sd["items"][0]["construction_date"] = "2026-09-15"
    order.structured_data = sd
    flag_modified(order, "structured_data")
    pg_session.flush()
    pg_session.expire_all()

    rebuilt = (
        pg_session.query(OrderScheduleDate)
        .filter_by(order_id=order.id, kind="construction", item_index=0)
        .one()
    )
    assert rebuilt.date == "2026-09-15"
    # rebuild 후에도 같은 identity UUID 로 재결합(유실 0).
    assert rebuilt.item_id == linked_uuid
