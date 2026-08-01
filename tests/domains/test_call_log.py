"""CALL-LOG-01: 통화 기록 command(CALL_LOGGED) one-tx·orthogonal 계약 테스트 (red→green).

통화 append 를 정본 command ``CALL_LOGGED`` 로 확정한다: REV-00
``execute_order_mutation`` 경유로 version bump + idempotency receipt + OrderEvent parity
를 **한 transaction** 에 묶고, ``sd['calls']`` 에만 append 1(중복 없음)하며,
main/logistics/hold/AS/delete **축은 절대 불변**(orthogonal write)임을 증명한다.

actor 권한(STAFF+CS/SALES 또는 ADMIN/MANAGER 200, 그 외 403+DB/event 0)은 AUTH-01 정책
가드로 enforce 되므로 ``policy_on`` 픽스처로 명시 활성화한다(test_auth_enforcement 준용).
"""

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, OrderMutationReceipt, User
from foms.services.orders.state_axes import read_state_axes

CALL_LOG_POLICY_ID = "ERP_EDIT"


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
        customer_name="통화 대상",
        phone="010-1234-5678",
        address="Seoul",
        product="Wardrobe",
        status=status,
        manager_name="Alice",
        is_erp_order=True,
        erp_stage_code=status,
        structured_data=structured_data
        if structured_data is not None
        else {"workflow": {"stage": status}},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _fresh(oid):
    db_session.remove()
    return db_session.query(Order).filter_by(id=oid).first()


# --------------------------------------------------------------------------
# one-tx: version bump + receipt + OrderEvent parity (중복 없음)
# --------------------------------------------------------------------------
def test_call_logged_bumps_version_and_writes_receipt(client, app):
    """통화 append 는 mutation_version++ · receipt 1 · OrderEvent(CALL_LOGGED) 1 을 한 tx 에."""
    _login(client, username="cs-onetx", role="STAFF", team="CS")
    oid = _create_order()
    before = _fresh(oid).mutation_version

    resp = client.post(f"/api/orders/{oid}/call-log", json={"result": "connected", "memo": "확인"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.get_json()["data"]["calls_count"] == 1

    fresh = _fresh(oid)
    assert fresh.mutation_version == before + 1  # 정확히 1회 bump
    assert len(fresh.structured_data["calls"]) == 1

    events = db_session.query(OrderEvent).filter_by(order_id=oid, event_type="CALL_LOGGED").all()
    assert len(events) == 1  # 중복 없음

    receipts = db_session.query(OrderMutationReceipt).filter_by(policy_id=CALL_LOG_POLICY_ID)
    assert receipts.count() == 1  # receipt 1건 기록


# --------------------------------------------------------------------------
# orthogonal write: main/logistics/hold/AS/delete 축 절대 불변
# --------------------------------------------------------------------------
def test_call_logged_leaves_all_state_axes_unchanged(client, app):
    """통화 append 후 canonical 5축(main/logistics/hold/AS/delete)이 완전 불변."""
    _login(client, username="cs-orth", role="STAFF", team="CS")
    oid = _create_order(
        structured_data={
            "workflow": {"stage": "DRAWING", "hold": {"active": True, "reason": "대기"}},
            "shipment": {"logistics_status": "SCHEDULED"},
        },
        status="DRAWING",
    )
    axes_before = read_state_axes(_fresh(oid))

    resp = client.post(f"/api/orders/{oid}/call-log", json={"result": "connected"})
    assert resp.status_code == 200, resp.get_data(as_text=True)

    axes_after = read_state_axes(_fresh(oid))
    assert axes_after.main == axes_before.main
    assert axes_after.logistics == axes_before.logistics
    assert axes_after.hold == axes_before.hold
    assert axes_after.as_status == axes_before.as_status
    assert axes_after.deleted == axes_before.deleted


def test_call_log_ignores_non_whitelisted_body_fields(client, app):
    """generic structured PUT 아님: body 의 workflow/quest 등 임의 키는 무시(축·quest 불변)."""
    _login(client, username="cs-nogeneric", role="STAFF", team="CS")
    oid = _create_order(
        structured_data={"workflow": {"stage": "RECEIVED"}, "quest": {"level": 3}}
    )

    resp = client.post(
        f"/api/orders/{oid}/call-log",
        json={
            "result": "connected",
            "workflow": {"stage": "COMPLETED"},  # 무시되어야 함
            "quest": {"level": 99},              # 무시되어야 함
        },
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)

    sd = _fresh(oid).structured_data
    assert sd["workflow"]["stage"] == "RECEIVED"  # 축 불변
    assert sd["quest"]["level"] == 3              # quest 불변
    assert len(sd["calls"]) == 1


# --------------------------------------------------------------------------
# idempotency: same key → append 1 (replay, 중복 없음)
# --------------------------------------------------------------------------
def test_call_logged_same_idempotency_key_appends_once(client, app):
    """같은 Idempotency-Key 재요청은 replay — calls append 1 · event 1 · version 1회 bump."""
    _login(client, username="cs-idem", role="STAFF", team="CS")
    oid = _create_order()
    before = _fresh(oid).mutation_version
    headers = {"Idempotency-Key": "11111111-1111-1111-1111-111111111111"}
    body = {"result": "connected", "memo": "한 번만"}

    r1 = client.post(f"/api/orders/{oid}/call-log", json=body, headers=headers)
    r2 = client.post(f"/api/orders/{oid}/call-log", json=body, headers=headers)
    assert r1.status_code == 200 and r2.status_code == 200, (r1.get_data(as_text=True), r2.get_data(as_text=True))

    fresh = _fresh(oid)
    assert len(fresh.structured_data["calls"]) == 1        # append 1 (replay)
    assert fresh.mutation_version == before + 1            # 1회만 bump
    assert (
        db_session.query(OrderEvent).filter_by(order_id=oid, event_type="CALL_LOGGED").count() == 1
    )


# --------------------------------------------------------------------------
# If-Match(mutation_version) 낙관 잠금
# --------------------------------------------------------------------------
def test_call_logged_stale_if_match_conflicts_and_no_change(client, app):
    """stale If-Match → 409 · calls/version/event 완전 불변."""
    _login(client, username="cs-stale", role="STAFF", team="CS")
    oid = _create_order()
    before = _fresh(oid).mutation_version

    resp = client.post(
        f"/api/orders/{oid}/call-log",
        json={"result": "connected"},
        headers={"If-Match": str(before + 5)},  # stale
    )
    assert resp.status_code == 409, resp.get_data(as_text=True)

    fresh = _fresh(oid)
    assert "calls" not in (fresh.structured_data or {})   # 상태 불변
    assert fresh.mutation_version == before               # version 불변
    assert db_session.query(OrderEvent).filter_by(order_id=oid).count() == 0


def test_call_logged_matching_if_match_succeeds(client, app):
    """정확한 If-Match(현재 version) → 200 저장."""
    _login(client, username="cs-match", role="STAFF", team="CS")
    oid = _create_order()
    current = _fresh(oid).mutation_version

    resp = client.post(
        f"/api/orders/{oid}/call-log",
        json={"result": "connected"},
        headers={"If-Match": str(current)},
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert len(_fresh(oid).structured_data["calls"]) == 1


# --------------------------------------------------------------------------
# actor 권한 (AUTH-01 정책 가드) — 200 vs 403+DB/event 0
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role,team", [
    ("STAFF", "CS"),
    ("STAFF", "SALES"),
    ("ADMIN", None),
    ("MANAGER", None),
])
def test_call_logged_allows_eligible_actors(client, app, policy_on, role, team):
    """STAFF+CS/SALES · ADMIN · MANAGER 는 통화 기록 200."""
    _login(client, username=f"ok-{role}-{team}", role=role, team=team)
    oid = _create_order()
    resp = client.post(f"/api/orders/{oid}/call-log", json={"result": "connected"})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.headers.get("X-Auth-Policy") is None
    assert len(_fresh(oid).structured_data["calls"]) == 1


@pytest.mark.parametrize("role,team", [
    ("VIEWER", None),
    ("STAFF", "DRAWING"),
    ("STAFF", "PRODUCTION"),
])
def test_call_logged_denies_ineligible_actors(client, app, policy_on, role, team):
    """VIEWER·타팀 STAFF 는 403(X-Auth-Policy denied) · DB/event 0."""
    _login(client, username=f"no-{role}-{team}", role=role, team=team)
    oid = _create_order()
    resp = client.post(f"/api/orders/{oid}/call-log", json={"result": "connected"})
    assert resp.status_code == 403, resp.get_data(as_text=True)
    assert resp.headers.get("X-Auth-Policy") == "denied"

    fresh = _fresh(oid)
    assert "calls" not in (fresh.structured_data or {})
    assert db_session.query(OrderEvent).filter_by(order_id=oid).count() == 0
    assert db_session.query(OrderMutationReceipt).count() == 0
