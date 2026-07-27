"""STORAGE-WRITER-01: 수납장 대시보드 typed field adapter 계약 테스트 (red→green).

수납장 대시보드의 인라인 편집을 generic field adapter 대신 **typed adapter**로 확정한다:
cabinet_status 는 enum·Production/Shipment 정책, shipping_fee 는 정수·Finance 정책으로
in-handler enforce 하고, REV-00 ``execute_order_mutation`` 경유로 version bump + receipt +
OrderEvent 를 한 transaction 에 묶는다. generic field coercion(임의 필드/타입)은 거부하고,
main/logistics/settlement 축은 **완전 불변**임을 증명한다.

권한은 handler in-handler 정책이 항상 enforce 하므로 AUTH_POLICY_ENABLED 없이도 통과한다.
"""

import copy

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, OrderMutationReceipt, User

CABINET_POLICY_ID = "CABINET_STATUS_CHANGED"
SHIPPING_POLICY_ID = "SHIPPING_FEE_CHANGED"


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼
# --------------------------------------------------------------------------
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


def _create_cabinet_order(*, cabinet_status="RECEIVED", shipping_fee=0, structured_data=None):
    order = Order(
        received_date="2026-04-07",
        customer_name="수납장 고객",
        phone="010-1234-5678",
        address="Seoul",
        product="Cabinet",
        status="RECEIVED",
        manager_name="Alice",
        is_cabinet=True,
        cabinet_status=cabinet_status,
        shipping_fee=shipping_fee,
        structured_data=structured_data if structured_data is not None else {},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _fresh(oid):
    db_session.remove()
    return db_session.query(Order).filter_by(id=oid).first()


def _post(client, oid, field, value, **kwargs):
    return client.post(f"/api/storage_dashboard/order/{oid}/field", json={"field": field, "value": value}, **kwargs)


# --------------------------------------------------------------------------
# cabinet enum: 유효 값만 저장, 임의 값 거부(422)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("value", ["RECEIVED", "IN_PRODUCTION", "SHIPPED"])
def test_cabinet_status_accepts_enum_values(client, app, value):
    """유효한 cabinet enum 값은 200 저장."""
    _login(client, username=f"cs-{value}", role="STAFF", team="CS")
    oid = _create_cabinet_order()
    resp = _post(client, oid, "cabinet_status", value)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _fresh(oid).cabinet_status == value


@pytest.mark.parametrize("value", ["BOGUS", "completed", "", 3, None])
def test_cabinet_status_rejects_non_enum(client, app, value):
    """enum 밖 값은 422 · DB 불변(generic coercion 아님)."""
    _login(client, username="cs-bad-enum", role="STAFF", team="CS")
    oid = _create_cabinet_order(cabinet_status="RECEIVED")
    before_ver = _fresh(oid).mutation_version
    resp = _post(client, oid, "cabinet_status", value)
    assert resp.status_code == 422, resp.get_data(as_text=True)
    fresh = _fresh(oid)
    assert fresh.cabinet_status == "RECEIVED"      # 불변
    assert fresh.mutation_version == before_ver    # version 불변
    assert db_session.query(OrderEvent).filter_by(order_id=oid).count() == 0


# --------------------------------------------------------------------------
# cabinet 정책: Production/Shipment 허용, VIEWER·타팀 403
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role,team", [
    ("STAFF", "CS"), ("STAFF", "SALES"), ("STAFF", "PRODUCTION"),
    ("STAFF", "SHIPMENT"), ("ADMIN", None), ("MANAGER", None),
])
def test_cabinet_status_allows_production_or_shipment(client, app, role, team):
    """cabinet 변경 = Production∪Shipment 정책(CS/SALES/PRODUCTION/SHIPMENT + ADMIN/MANAGER)."""
    _login(client, username=f"ok-cab-{role}-{team}", role=role, team=team)
    oid = _create_cabinet_order()
    resp = _post(client, oid, "cabinet_status", "IN_PRODUCTION")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _fresh(oid).cabinet_status == "IN_PRODUCTION"


@pytest.mark.parametrize("role,team", [("VIEWER", None), ("STAFF", "DRAWING")])
def test_cabinet_status_denies_ineligible(client, app, role, team):
    """VIEWER·무권한 팀은 403 · DB/event/receipt 0."""
    _login(client, username=f"no-cab-{role}-{team}", role=role, team=team)
    oid = _create_cabinet_order(cabinet_status="RECEIVED")
    resp = _post(client, oid, "cabinet_status", "SHIPPED")
    assert resp.status_code == 403, resp.get_data(as_text=True)
    fresh = _fresh(oid)
    assert fresh.cabinet_status == "RECEIVED"
    assert db_session.query(OrderEvent).filter_by(order_id=oid).count() == 0
    assert db_session.query(OrderMutationReceipt).count() == 0


# --------------------------------------------------------------------------
# shipping fee: 정수만, 비정수 거부(422). Finance 정책.
# --------------------------------------------------------------------------
def test_shipping_fee_accepts_integer(client, app):
    """정수 배송비는 200 저장(재정의 없이 원값)."""
    _login(client, username="cs-fee", role="STAFF", team="CS")
    oid = _create_cabinet_order(shipping_fee=0)
    resp = _post(client, oid, "shipping_fee", 15000)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _fresh(oid).shipping_fee == 15000


@pytest.mark.parametrize("value", ["abc", 12.5, "12.5", -100, None, True])
def test_shipping_fee_rejects_non_integer(client, app, value):
    """비정수/음수는 422 · DB 불변."""
    _login(client, username="cs-badfee", role="STAFF", team="CS")
    oid = _create_cabinet_order(shipping_fee=500)
    resp = _post(client, oid, "shipping_fee", value)
    assert resp.status_code == 422, resp.get_data(as_text=True)
    assert _fresh(oid).shipping_fee == 500


@pytest.mark.parametrize("role,team", [
    ("STAFF", "CS"), ("STAFF", "SALES"), ("ADMIN", None), ("MANAGER", None),
])
def test_shipping_fee_allows_finance_actors(client, app, role, team):
    """shipping fee = Finance 정책(CS/SALES + ADMIN/MANAGER) 200."""
    _login(client, username=f"ok-fee-{role}-{team}", role=role, team=team)
    oid = _create_cabinet_order()
    resp = _post(client, oid, "shipping_fee", 9000)
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _fresh(oid).shipping_fee == 9000


@pytest.mark.parametrize("role,team", [
    ("VIEWER", None), ("STAFF", "PRODUCTION"), ("STAFF", "SHIPMENT"), ("STAFF", "DRAWING"),
])
def test_shipping_fee_denies_non_finance(client, app, role, team):
    """Finance 아니면 403 · 배송비 불변(PRODUCTION/SHIPMENT 도 배송비는 불가)."""
    _login(client, username=f"no-fee-{role}-{team}", role=role, team=team)
    oid = _create_cabinet_order(shipping_fee=700)
    resp = _post(client, oid, "shipping_fee", 12000)
    assert resp.status_code == 403, resp.get_data(as_text=True)
    assert _fresh(oid).shipping_fee == 700


# --------------------------------------------------------------------------
# generic field coercion 거부: 임의 필드는 400
# --------------------------------------------------------------------------
@pytest.mark.parametrize("field", ["customer_name", "status", "is_cabinet", "structured_data", "notes"])
def test_rejects_generic_field(client, app, field):
    """typed 두 필드 밖 임의 필드는 400 · 대상 컬럼 불변(generic coercion 금지)."""
    _login(client, username=f"cs-generic-{field}", role="STAFF", team="CS")
    oid = _create_cabinet_order()
    before = _fresh(oid)
    before_name, before_status = before.customer_name, before.status
    resp = _post(client, oid, field, "HACKED")
    assert resp.status_code == 400, resp.get_data(as_text=True)
    fresh = _fresh(oid)
    assert fresh.customer_name == before_name
    assert fresh.status == before_status
    assert db_session.query(OrderEvent).filter_by(order_id=oid).count() == 0


# --------------------------------------------------------------------------
# REV-00 one-tx: version bump + receipt + OrderEvent
# --------------------------------------------------------------------------
def test_cabinet_write_bumps_version_receipt_event(client, app):
    """cabinet 저장 = mutation_version++ · receipt 1(CABINET_STATUS_CHANGED) · event 1 한 tx."""
    _login(client, username="cs-onetx", role="STAFF", team="CS")
    oid = _create_cabinet_order(cabinet_status="RECEIVED")
    before = _fresh(oid).mutation_version

    resp = _post(client, oid, "cabinet_status", "IN_PRODUCTION")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["data"]["mutation_receipt"]
    assert resp.headers.get("Cache-Control") == "private, no-store"

    fresh = _fresh(oid)
    assert fresh.mutation_version == before + 1
    assert db_session.query(OrderEvent).filter_by(
        order_id=oid, event_type=CABINET_POLICY_ID).count() == 1
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id=CABINET_POLICY_ID).count() == 1


def test_shipping_write_bumps_version_and_event(client, app):
    """shipping fee 저장도 version++ · event(SHIPPING_FEE_CHANGED) 1 · receipt 1."""
    _login(client, username="cs-fee-tx", role="STAFF", team="CS")
    oid = _create_cabinet_order(shipping_fee=0)
    before = _fresh(oid).mutation_version

    resp = _post(client, oid, "shipping_fee", 33000)
    assert resp.status_code == 200, resp.get_data(as_text=True)

    fresh = _fresh(oid)
    assert fresh.mutation_version == before + 1
    assert fresh.shipping_fee == 33000
    assert db_session.query(OrderEvent).filter_by(
        order_id=oid, event_type=SHIPPING_POLICY_ID).count() == 1
    assert db_session.query(OrderMutationReceipt).filter_by(policy_id=SHIPPING_POLICY_ID).count() == 1


# --------------------------------------------------------------------------
# If-Match(mutation_version) 낙관 잠금
# --------------------------------------------------------------------------
def test_stale_if_match_conflicts_and_no_change(client, app):
    """stale If-Match → 409 · cabinet_status/version/event 완전 불변."""
    _login(client, username="cs-stale", role="STAFF", team="CS")
    oid = _create_cabinet_order(cabinet_status="RECEIVED")
    before = _fresh(oid).mutation_version

    resp = _post(client, oid, "cabinet_status", "SHIPPED", headers={"If-Match": str(before + 5)})
    assert resp.status_code == 409, resp.get_data(as_text=True)

    fresh = _fresh(oid)
    assert fresh.cabinet_status == "RECEIVED"
    assert fresh.mutation_version == before
    assert db_session.query(OrderEvent).filter_by(order_id=oid).count() == 0


def test_matching_if_match_succeeds(client, app):
    """정확한 If-Match(현재 version) → 200 저장."""
    _login(client, username="cs-match", role="STAFF", team="CS")
    oid = _create_cabinet_order(cabinet_status="RECEIVED")
    current = _fresh(oid).mutation_version

    resp = _post(client, oid, "cabinet_status", "IN_PRODUCTION", headers={"If-Match": str(current)})
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _fresh(oid).cabinet_status == "IN_PRODUCTION"


def test_bad_if_match_format_rejected(client, app):
    """비정수 If-Match 는 삼키지 않고 400 · DB 불변."""
    _login(client, username="cs-badmatch", role="STAFF", team="CS")
    oid = _create_cabinet_order(cabinet_status="RECEIVED")
    resp = _post(client, oid, "cabinet_status", "SHIPPED", headers={"If-Match": "not-a-number"})
    assert resp.status_code == 400, resp.get_data(as_text=True)
    assert _fresh(oid).cabinet_status == "RECEIVED"


# --------------------------------------------------------------------------
# orthogonal: main/logistics/settlement 절대 불변
# --------------------------------------------------------------------------
def test_storage_write_leaves_main_logistics_settlement_unchanged(client, app):
    """typed 저장 후 main(status/workflow)·logistics·settlement JSONB 완전 불변."""
    _login(client, username="cs-orth", role="STAFF", team="CS")
    seed = {
        "workflow": {"stage": "DRAWING"},
        "shipment": {"logistics_status": "SCHEDULED"},
        "settlement": {"balance": 500000, "deposit": 100000},
    }
    oid = _create_cabinet_order(cabinet_status="RECEIVED", structured_data=copy.deepcopy(seed))
    before = _fresh(oid)
    before_status = before.status

    resp = _post(client, oid, "cabinet_status", "SHIPPED")
    assert resp.status_code == 200, resp.get_data(as_text=True)

    fresh = _fresh(oid)
    assert fresh.cabinet_status == "SHIPPED"          # 이 축만 변경
    assert fresh.status == before_status              # main scalar 불변
    assert fresh.structured_data == seed              # JSONB(main/logistics/settlement) 불변
