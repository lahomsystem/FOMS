"""ERP-ESTIMATE-01: 주문 견적 CRUD one-tx·parent scope 계약 테스트 (red→green).

견적서(OrderEstimate)는 부모 Order 의 child 다. create/update/draft-delete/issued-cancel
을 정본 command 로 확정한다: REV-00 ``execute_order_mutation`` 경유로 **부모 Order 의
mutation_version bump + idempotency receipt + OrderEvent parity 를 한 transaction** 에 묶고,
parent scope(cross-order 거부)·CS/SALES/Admin 권한(VIEWER 403)·stale If-Match 409 불변을
증명한다. issued estimate 는 hard-delete 하지 않고(soft cancel 만), draft-delete 는 draft
상태에서만 물리 삭제한다.
"""

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEstimate, OrderEvent, OrderMutationReceipt, User
from foms.api.erp_estimates import (
    CMD_ESTIMATE_CREATE,
    CMD_ESTIMATE_UPDATE,
    CMD_ESTIMATE_DELETE,
    CMD_ESTIMATE_CANCEL,
    EVENT_ESTIMATE_CREATED,
    EVENT_ESTIMATE_UPDATED,
    EVENT_ESTIMATE_DELETED,
    EVENT_ESTIMATE_CANCELLED,
)


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼
# --------------------------------------------------------------------------
@pytest.fixture
def policy_on(app):
    """이 테스트 동안만 AUTH-01 정책 가드를 강제 활성화하고 원복한다."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


def _login(client, *, username, role, team=None):
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    uid = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = username
        sess["role"] = role
    return uid


def _create_order(structured_data=None, status="RECEIVED"):
    order = Order(
        received_date="2026-04-07",
        customer_name="견적 대상",
        phone="010-1234-5678",
        address="Seoul",
        product="Wardrobe",
        status=status,
        manager_name="Alice",
        is_erp_order=True,
        erp_stage_code=status,
        structured_data=structured_data
        if structured_data is not None
        else {"items": [{"product_name": "장", "quantity": 1, "price": 500000}]},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _seed_estimate(order_id, *, status="DRAFT", number="20260407_1", notes=None):
    estimate = OrderEstimate(
        order_id=order_id,
        estimate_number=number,
        customer_name="견적 대상",
        estimate_date="2026-04-07",
        items=[{"product_name": "장", "quantity": 1, "unit_price": 500000, "amount": 500000}],
        total_amount=500000,
        status=status,
        notes=notes,
    )
    db_session.add(estimate)
    db_session.commit()
    return estimate.id


def _fresh_order(oid):
    db_session.remove()
    return db_session.query(Order).filter_by(id=oid).first()


def _fresh_estimate(eid):
    db_session.remove()
    return db_session.query(OrderEstimate).filter_by(id=eid).first()


# --------------------------------------------------------------------------
# create: version bump + receipt + OrderEvent parity (one tx)
# --------------------------------------------------------------------------
def test_create_bumps_version_receipt_and_event(client, app):
    """견적 생성은 부모 Order version++ · receipt(ESTIMATE_CREATE) 1 · OrderEvent 1 을 한 tx 에."""
    _login(client, username="cs-create", role="STAFF", team="CS")
    oid = _create_order()
    before = _fresh_order(oid).mutation_version

    resp = client.post(f"/api/orders/{oid}/estimates", json={})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True
    assert body["data"]["mutation_receipt"]
    assert resp.headers.get("Cache-Control") == "private, no-store"

    assert _fresh_order(oid).mutation_version == before + 1  # 정확히 1회 bump
    assert db_session.query(OrderEstimate).filter_by(order_id=oid).count() == 1
    assert (
        db_session.query(OrderEvent)
        .filter_by(order_id=oid, event_type=EVENT_ESTIMATE_CREATED)
        .count()
        == 1
    )
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id=CMD_ESTIMATE_CREATE).count() == 1


# --------------------------------------------------------------------------
# update: version bump + receipt + event, 필드 반영
# --------------------------------------------------------------------------
def test_update_bumps_version_receipt_and_event(client, app):
    """견적 수정은 부모 version++ · receipt(ESTIMATE_UPDATE) · OrderEvent(UPDATED) 1 을 한 tx 에."""
    _login(client, username="cs-update", role="STAFF", team="CS")
    oid = _create_order()
    eid = _seed_estimate(oid)
    before = _fresh_order(oid).mutation_version

    resp = client.put(f"/api/estimates/{eid}", json={"notes": "수정메모", "customer_name": "변경고객"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    fresh = _fresh_estimate(eid)
    assert fresh.notes == "수정메모"
    assert fresh.customer_name == "변경고객"
    assert _fresh_order(oid).mutation_version == before + 1
    assert (
        db_session.query(OrderEvent)
        .filter_by(order_id=oid, event_type=EVENT_ESTIMATE_UPDATED)
        .count()
        == 1
    )
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id=CMD_ESTIMATE_UPDATE).count() == 1


# --------------------------------------------------------------------------
# draft-delete: 물리 삭제 + one tx (draft 상태에서만)
# --------------------------------------------------------------------------
def test_draft_delete_hard_deletes_with_onetx(client, app):
    """DRAFT 삭제는 물리 삭제 · 부모 version++ · OrderEvent(DELETED) · receipt(ESTIMATE_DELETE)."""
    _login(client, username="cs-draftdel", role="STAFF", team="CS")
    oid = _create_order()
    eid = _seed_estimate(oid, status="DRAFT")
    before = _fresh_order(oid).mutation_version

    resp = client.delete(f"/api/estimates/{eid}")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["data"]["cancelled"] is False

    assert _fresh_estimate(eid) is None  # 물리 삭제됨
    assert _fresh_order(oid).mutation_version == before + 1
    assert (
        db_session.query(OrderEvent)
        .filter_by(order_id=oid, event_type=EVENT_ESTIMATE_DELETED)
        .count()
        == 1
    )
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id=CMD_ESTIMATE_DELETE).count() == 1


# --------------------------------------------------------------------------
# issued-cancel: soft-cancel 만 (hard-delete 금지)
# --------------------------------------------------------------------------
def test_issued_delete_soft_cancels_never_hard_deletes(client, app):
    """ISSUED 견적 DELETE 는 CANCELLED soft-cancel · 행 보존(hard-delete 금지) · one tx."""
    _login(client, username="cs-issued", role="STAFF", team="CS")
    oid = _create_order()
    eid = _seed_estimate(oid, status="ISSUED")
    before = _fresh_order(oid).mutation_version

    resp = client.delete(f"/api/estimates/{eid}")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["data"]["cancelled"] is True

    fresh = _fresh_estimate(eid)
    assert fresh is not None                # 물리 삭제 금지 — 행 보존
    assert fresh.status == "CANCELLED"      # soft-cancel
    assert _fresh_order(oid).mutation_version == before + 1
    assert (
        db_session.query(OrderEvent)
        .filter_by(order_id=oid, event_type=EVENT_ESTIMATE_CANCELLED)
        .count()
        == 1
    )
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id=CMD_ESTIMATE_CANCEL).count() == 1
    # draft hard-delete 경로는 타지 않았다.
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id=CMD_ESTIMATE_DELETE).count() == 0


# --------------------------------------------------------------------------
# parent scope: cross-order 재부모화 거부 (payload order_id 무시)
# --------------------------------------------------------------------------
def test_update_is_parent_scoped_ignores_payload_order_id(client, app):
    """estimate 는 부모 Order 에 종속 — payload order_id 로 다른 order 로 재부모화 불가.

    수정은 진짜 부모(A)만 잠그고 bump 하며, 무관한 order(B) 는 절대 건드리지 않는다.
    """
    _login(client, username="cs-parent", role="STAFF", team="CS")
    oid_a = _create_order()
    oid_b = _create_order()
    eid = _seed_estimate(oid_a, number="20260407_2")
    before_a = _fresh_order(oid_a).mutation_version
    before_b = _fresh_order(oid_b).mutation_version

    resp = client.put(f"/api/estimates/{eid}", json={"order_id": oid_b, "notes": "cross"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    fresh = _fresh_estimate(eid)
    assert fresh.order_id == oid_a          # 재부모화되지 않음
    assert fresh.notes == "cross"           # 허용 필드는 반영
    assert _fresh_order(oid_a).mutation_version == before_a + 1  # 부모만 bump
    assert _fresh_order(oid_b).mutation_version == before_b      # 무관 order 불변
    assert db_session.query(OrderEvent).filter_by(order_id=oid_b).count() == 0


# --------------------------------------------------------------------------
# If-Match(mutation_version) 낙관 잠금
# --------------------------------------------------------------------------
def test_stale_if_match_conflicts_and_no_change(client, app):
    """stale If-Match → 409 · estimate/version/event 완전 불변."""
    _login(client, username="cs-stale", role="STAFF", team="CS")
    oid = _create_order()
    eid = _seed_estimate(oid, notes="원본")
    before = _fresh_order(oid).mutation_version

    resp = client.put(
        f"/api/estimates/{eid}",
        json={"notes": "덮어쓰기"},
        headers={"If-Match": str(before + 5)},  # stale
    )
    assert resp.status_code == 409, resp.get_data(as_text=True)

    assert _fresh_estimate(eid).notes == "원본"            # 상태 불변
    assert _fresh_order(oid).mutation_version == before    # version 불변
    assert (
        db_session.query(OrderEvent)
        .filter_by(order_id=oid, event_type=EVENT_ESTIMATE_UPDATED)
        .count()
        == 0
    )


def test_matching_if_match_succeeds(client, app):
    """정확한 If-Match(현재 version) → 200 저장."""
    _login(client, username="cs-match", role="STAFF", team="CS")
    oid = _create_order()
    eid = _seed_estimate(oid, notes="원본")
    current = _fresh_order(oid).mutation_version

    resp = client.put(
        f"/api/estimates/{eid}",
        json={"notes": "적용"},
        headers={"If-Match": str(current)},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _fresh_estimate(eid).notes == "적용"


# --------------------------------------------------------------------------
# actor 권한 (ERP_EDIT) — CS/SALES/ADMIN/MANAGER 허용, VIEWER/타팀 거부
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role,team", [
    ("STAFF", "CS"),
    ("STAFF", "SALES"),
    ("ADMIN", None),
    ("MANAGER", None),
])
def test_create_allows_eligible_actors(client, app, policy_on, role, team):
    """STAFF+CS/SALES · ADMIN · MANAGER 는 견적 생성 201."""
    _login(client, username=f"ok-{role}-{team}", role=role, team=team)
    oid = _create_order()
    resp = client.post(f"/api/orders/{oid}/estimates", json={})
    assert resp.status_code == 201, resp.get_data(as_text=True)
    assert resp.headers.get("X-Auth-Policy") is None
    assert db_session.query(OrderEstimate).filter_by(order_id=oid).count() == 1


@pytest.mark.parametrize("role,team", [
    ("VIEWER", None),
    ("STAFF", "DRAWING"),
    ("STAFF", "PRODUCTION"),
])
def test_create_denies_ineligible_actors(client, app, policy_on, role, team):
    """VIEWER·타팀 STAFF 는 403(X-Auth-Policy denied) · DB/event/receipt 0."""
    _login(client, username=f"no-{role}-{team}", role=role, team=team)
    oid = _create_order()
    resp = client.post(f"/api/orders/{oid}/estimates", json={})
    assert resp.status_code == 403, resp.get_data(as_text=True)
    assert resp.headers.get("X-Auth-Policy") == "denied"

    assert db_session.query(OrderEstimate).filter_by(order_id=oid).count() == 0
    assert db_session.query(OrderEvent).filter_by(order_id=oid).count() == 0
    assert db_session.query(OrderMutationReceipt).count() == 0


def test_viewer_denied_at_route_level_without_guard(client, app):
    """AUTH 가드 비활성(기본 TESTING) 컨텍스트에서도 route 레벨 enforce 로 VIEWER 403 · write 0."""
    _login(client, username="viewer-route", role="VIEWER", team=None)
    oid = _create_order()
    resp = client.post(f"/api/orders/{oid}/estimates", json={})
    assert resp.status_code == 403, resp.get_data(as_text=True)
    assert db_session.query(OrderEstimate).filter_by(order_id=oid).count() == 0
    assert db_session.query(OrderMutationReceipt).count() == 0
