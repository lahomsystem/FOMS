"""주문 금액·담당자·상태 저장 팀 범위 (SPEC 2026-10-20-order-edit-team-scope).

역할표(§2.1)는 도면·생산·시공·출고 팀에게 일반 structured form·main-stage 쓰기를
금지한다. 구조화 폼 PUT/PATCH·옛 편집 폼 POST·상태 변경 2경로는 ``ERP_EDIT``
(영업·CS + MEASURE→SALES·회계→CS)로, ``/api/update_order_field`` 는 칸별로
(담당자·main-stage 상태 = ``ERP_EDIT``, 물류 보드 상태 = ``SHIPMENT_EDIT``) 좁힌다.
"""

import json

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User

_GUARDED = [
    ("PUT", "/api/orders/{oid}/structured", {"structured_data": {}}),
    ("PATCH", "/api/orders/{oid}/structured/fields", {"fields": {}}),
    ("POST", "/edit/{oid}", None),
    ("POST", "/api/update_order_status", {"order_id": "{oid}", "status": "MEASURE"}),
    ("POST", "/api/bulk_update_order_status", {"order_ids": ["{oid}"], "status": "MEASURE"}),
]

_GUARDED_ENDPOINTS = (
    "erp_orders_structured.api_put_order_structured",
    "erp_orders_structured.api_patch_order_structured_fields",
    "order_edit.edit_order",
    "orders.update_order_status",
    "orders.bulk_update_order_status",
)

_DENIED = [
    ("VIEWER", None),
    ("STAFF", "PRODUCTION"),
    ("STAFF", "DRAWING"),
    ("STAFF", "CONSTRUCTION"),
    ("STAFF", "SHIPMENT"),
]

_ALLOWED = [
    ("ADMIN", None),
    ("MANAGER", None),
    ("STAFF", "CS"),
    ("STAFF", "SALES"),
    ("STAFF", "ACCOUNTING"),
    ("STAFF", "MEASURE"),
]


@pytest.fixture
def policy_on(app):
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


_seq = 0


def _make_user(role, team):
    global _seq
    _seq += 1
    user = User(
        username=f"scope_{role}_{team}_{_seq}",
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{role}-{team}-{_seq}",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_order():
    order = Order(
        received_date="2026-10-20",
        customer_name="범위 대상",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        status="RECEIVED",
        manager_name="원래담당",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "RECEIVED"}},
        erp_stage_code="RECEIVED",
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _fill(body, oid):
    if body is None:
        return None
    return json.loads(json.dumps(body).replace('"{oid}"', str(oid)))


def _snapshot(oid):
    db_session.expire_all()
    order = db_session.get(Order, oid)
    return order.status, order.manager_name, json.dumps(order.structured_data, sort_keys=True)


def _guard_blocked(caplog):
    # /api 는 403 JSON, HTML 편집 폼은 홈 redirect 라 응답만으론 handler 의 redirect 와
    # 못 가른다 — 가드가 남기는 경고 줄로 판정한다.
    return any("auth-policy blocked" in r.getMessage() for r in caplog.records)


def test_manifest_moves_order_form_endpoints_to_erp_edit():
    from foms.services.orders.order_mutation_policy import load_policy_manifest

    routes = load_policy_manifest()["routes"]
    assert {ep: routes[ep]["policy_id"] for ep in _GUARDED_ENDPOINTS} == {
        ep: "ERP_EDIT" for ep in _GUARDED_ENDPOINTS
    }


@pytest.mark.parametrize("role,team", _DENIED)
@pytest.mark.parametrize("method,path,body", _GUARDED)
def test_other_teams_cannot_save_order_form(client, app, policy_on, caplog, role, team, method, path, body):
    _login(client, _make_user(role, team))
    oid = _make_order()
    before = _snapshot(oid)

    payload = _fill(body, oid)
    if payload is None:
        resp = client.open(path.format(oid=oid), method=method, data={"customer_name": "바뀜"})
    else:
        resp = client.open(path.format(oid=oid), method=method, json=payload)

    assert resp.status_code in (403, 302), (role, team, path, resp.status_code)
    assert _guard_blocked(caplog), (role, team, path, resp.status_code)
    assert _snapshot(oid) == before


@pytest.mark.parametrize("role,team", _ALLOWED)
@pytest.mark.parametrize("method,path,body", _GUARDED)
def test_sales_side_passes_guard(client, app, policy_on, caplog, role, team, method, path, body):
    _login(client, _make_user(role, team))
    oid = _make_order()

    payload = _fill(body, oid)
    if payload is None:
        resp = client.open(path.format(oid=oid), method=method, data={})
    else:
        resp = client.open(path.format(oid=oid), method=method, json=payload)

    assert resp.headers.get("X-Auth-Policy") is None, (role, team, path, resp.status_code)
    assert not _guard_blocked(caplog), (role, team, path, resp.status_code)


def _field(client, oid, field, value):
    return client.post("/api/update_order_field", json={"order_id": oid, "field": field, "value": value})


@pytest.mark.parametrize("team", ["CONSTRUCTION", "DRAWING", "PRODUCTION"])
def test_update_order_field_manager_and_status_need_sales_side(client, app, policy_on, team):
    _login(client, _make_user("STAFF", team))
    oid = _make_order()
    before = _snapshot(oid)

    for field, value in (("manager_name", "다른사람"), ("status", "MEASURE"), ("status", "SCHEDULED")):
        resp = _field(client, oid, field, value)
        assert resp.status_code == 403, (team, field, value, resp.get_data(as_text=True))
        assert resp.get_json()["code"] == "FORBIDDEN"
    assert _snapshot(oid) == before


def test_update_order_field_shipment_logistics_only(client, app, policy_on):
    _login(client, _make_user("STAFF", "SHIPMENT"))
    oid = _make_order()

    assert _field(client, oid, "manager_name", "다른사람").status_code == 403
    assert _field(client, oid, "status", "MEASURE").status_code == 403
    resp = _field(client, oid, "status", "SCHEDULED")
    assert resp.status_code == 200, resp.get_data(as_text=True)


@pytest.mark.parametrize("role,team", [("STAFF", "CS"), ("STAFF", "MEASURE"), ("MANAGER", "SALES")])
def test_update_order_field_sales_side_can_change_manager(client, app, policy_on, role, team):
    _login(client, _make_user(role, team))
    oid = _make_order()

    resp = _field(client, oid, "manager_name", "새담당")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert _snapshot(oid)[1] == "새담당"


def test_update_order_field_other_fields_unchanged_for_construction(client, app, policy_on):
    """음성 대조군 — 담당자·상태가 아닌 칸은 지금처럼 시공팀도 쓴다."""
    _login(client, _make_user("STAFF", "CONSTRUCTION"))
    oid = _make_order()

    resp = _field(client, oid, "regional_cargo_sent", True)
    assert resp.status_code == 200, resp.get_data(as_text=True)
