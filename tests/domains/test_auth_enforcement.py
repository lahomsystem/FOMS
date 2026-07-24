"""AUTH-01: §2.1 권한 enforcement 계약 테스트 (red→green).

정책 가드는 ``AUTH_POLICY_ENABLED`` config(미지정 시 ``not TESTING``)로 켜진다. 기존 테스트는
``TESTING=True`` + 미지정이라 가드 OFF 로 통과하고(회귀 0), 이 파일만 ``policy_on`` 픽스처로
명시 활성화한 뒤 원복한다(cross-test 오염 방지 — write-guard 테스트 패턴 준용).

검증 대상:

* VIEWER hard deny — settlement/finance/order/drawing/packing/WDC master mutation 403(P0-3),
  ancillary allowlist 9종만 통과.
* production start/complete team-wide — PRODUCTION 팀 허용(P0-9 역전 수정), 무권한 팀 403.
* drawing/construction — ASSIGNMENT-00 user-ID row 기반(배정자만; JSONB 이름 미사용),
  MEASURE→SALES 정규화.
* ``/api``·``/erp/api`` 권한 실패 = 403 JSON(redirect 0 — P1-13/P1-18).
* static gate — 모든 state-changing route 가 policy_id 로 분류(미분류=red).
* 정상 role(CS/SALES/PRODUCTION/DRAWING assigned/MANAGER/ADMIN) 업무 흐름 유지(회귀 0).

가드는 handler 실행 **전** 차단이므로 거부 응답에는 ``X-Auth-Policy: denied`` 헤더가 붙는다.
이 헤더로 "정책이 막았는지"를 business 응답(4xx/5xx)과 구분한다.
"""

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderAssignment, User
from foms.services.orders.order_mutation_policy import (
    ANCILLARY_ALLOWLIST,
    POLICY_REGISTRY,
    load_policy_manifest,
)

_MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼
# --------------------------------------------------------------------------
@pytest.fixture
def policy_on(app):
    """이 테스트 동안만 정책 가드를 강제 활성화하고 원복한다."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


def _make_user(username, *, role="STAFF", team=None):
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
    return user


def _creds(user):
    """세션 로그인용 primitive (uid, username, role) — 요청 후 detach 대비 즉시 캡처."""
    return (user.id, user.username, user.role)


def _login(client, user_or_creds):
    """user 객체 또는 :func:`_creds` 튜플로 세션 로그인."""
    if isinstance(user_or_creds, tuple):
        uid, username, role = user_or_creds
    else:
        uid, username, role = _creds(user_or_creds)
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = username
        sess["role"] = role


def _make_order(stage_code="RECEIVED"):
    order = Order(
        received_date="2026-04-07",
        customer_name="권한 대상",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        status=stage_code,
        manager_name="Alice",
        is_erp_order=True,
        structured_data={"workflow": {"stage": stage_code}},
        erp_stage_code=stage_code,
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _assign(order_id, domain, user_id, *, source="TEAM_REPLACE"):
    from foms.services.datetime_kst import now_utc_naive

    row = OrderAssignment(
        order_id=order_id, domain=domain, user_id=user_id, source=source,
        active=True, assigned_at=now_utc_naive(), assigned_by_user_id=user_id,
    )
    db_session.add(row)
    db_session.commit()


def _denied(resp):
    """정책 가드가 거부했는가(403 + X-Auth-Policy)."""
    return resp.status_code == 403 and resp.headers.get("X-Auth-Policy") == "denied"


def _gate_passed(resp):
    """정책 가드를 통과했는가(막지 않았으면 business 응답이 무엇이든 True)."""
    return resp.headers.get("X-Auth-Policy") is None


# --------------------------------------------------------------------------
# static gate: 모든 mutation route 가 policy manifest 에 등재·분류되어야 한다
# --------------------------------------------------------------------------
def test_static_gate_every_mutation_route_classified(app):
    """url_map 의 모든 POST/PUT/PATCH/DELETE endpoint 가 policy_id 로 분류(미분류=fail)."""
    manifest = load_policy_manifest()
    routes = manifest.get("routes", {})

    url_map_endpoints = set()
    for rule in app.url_map.iter_rules():
        if (set(rule.methods or ()) & _MUTATION_METHODS) and "." in rule.endpoint:
            url_map_endpoints.add(rule.endpoint)

    manifest_endpoints = set(routes.keys())
    missing = sorted(url_map_endpoints - manifest_endpoints)
    stale = sorted(manifest_endpoints - url_map_endpoints)
    assert not missing, f"policy 미분류 state-changing route(=static fail): {missing}"
    assert not stale, f"manifest 에만 있고 url_map 에 없는 stale route: {stale}"

    for ep, meta in routes.items():
        mode = meta.get("mode")
        assert mode in ("guard", "exempt"), ep
        if mode == "exempt":
            assert meta.get("reason"), f"exempt route 사유 누락: {ep}"
        else:
            pid = meta.get("policy_id")
            assert pid in POLICY_REGISTRY, f"미등록 policy_id({pid}) — {ep}"


def test_ancillary_allowlist_is_exactly_nine(app):
    """§2.1 line 155 ancillary allowlist 는 정확히 9종이고 전부 viewer 허용이다."""
    assert len(ANCILLARY_ALLOWLIST) == 9
    for pid in ANCILLARY_ALLOWLIST:
        assert POLICY_REGISTRY[pid].viewer is True


# --------------------------------------------------------------------------
# VIEWER hard deny (P0-3)
# --------------------------------------------------------------------------
def test_viewer_denied_settlement_403_json_no_db_change(client, app, policy_on):
    """VIEWER settlement/issue → 403 JSON(X-Auth-Policy), redirect 0, DB 변화 0 (P0-3)."""
    _login(client, _make_user("viewer1", role="VIEWER"))
    oid = _make_order("COMPLETED")

    resp = client.post(f"/api/orders/{oid}/settlement/issue", json={"issued": True})

    assert _denied(resp), (resp.status_code, resp.headers.get("X-Auth-Policy"))
    assert resp.is_json
    assert resp.get_json()["success"] is False
    assert "Location" not in resp.headers  # redirect 아님

    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert "settlement" not in (saved.structured_data or {})  # handler 미실행 → DB0


@pytest.mark.parametrize("method,path,body", [
    ("POST", "/api/orders/{oid}/cash-receipt/issue", {}),
    ("POST", "/api/orders/{oid}/payment-confirm", {}),
    ("PUT", "/api/orders/{oid}/structured", {}),
    ("POST", "/api/orders/{oid}/transfer-drawing", {}),
    ("POST", "/api/erp/shipment/packing/{oid}", {}),
    ("POST", "/api/orders/{oid}/call-log", {"result": "connected"}),
])
def test_viewer_denied_across_business_surfaces(client, app, policy_on, method, path, body):
    """VIEWER 는 finance/order/drawing/packing/measurement mutation 전부 403."""
    _login(client, _make_user(f"viewer-{path[-6:]}", role="VIEWER"))
    oid = _make_order()
    resp = client.open(path.format(oid=oid), method=method, json=body)
    assert _denied(resp), (path, resp.status_code)


def test_viewer_denied_wdc_master_and_estimate(client, app, policy_on):
    """VIEWER 는 WDC master(product)·estimate save 도 403 (WDC 포함)."""
    _login(client, _make_user("viewer-wdc", role="VIEWER"))
    assert _denied(client.post("/api/wdcalculator/products", json={"name": "x"}))
    assert _denied(client.post("/api/wdcalculator/save-estimate", json={}))


def test_viewer_calculate_allowed_pure_calc(client, app, policy_on):
    """VIEWER 도 WDC calculate 는 통과(pure calc, DB 무변경 — §2.1 line 154)."""
    _login(client, _make_user("viewer-calc", role="VIEWER"))
    resp = client.post("/api/wdcalculator/calculate", json={})
    assert _gate_passed(resp)


# --------------------------------------------------------------------------
# VIEWER ancillary allowlist 9종 — 통과 (P1-24)
# --------------------------------------------------------------------------
def test_viewer_allowed_ancillary_surfaces(client, app, policy_on):
    """VIEWER 는 자기 notification/subscription/room/urgent-call ancillary 는 통과."""
    _login(client, _make_user("viewer-anc", role="VIEWER"))
    oid = _make_order()
    for method, path, body in [
        ("POST", "/erp/api/notifications/1/read", {}),
        ("POST", "/erp/api/notifications/1/ack", {}),
        ("POST", "/erp/api/notifications/push/subscribe", {"endpoint": "x"}),
        ("POST", "/api/chat/messages", {"room_id": 1, "text": "hi"}),
        ("POST", f"/erp/api/orders/{oid}/urgent-mention", {"target_user_id": 1}),
    ]:
        resp = client.open(path, method=method, json=body)
        assert _gate_passed(resp), (path, resp.status_code, resp.headers.get("X-Auth-Policy"))


# --------------------------------------------------------------------------
# production team-wide (P0-9 역전 수정)
# --------------------------------------------------------------------------
def test_production_team_can_start_and_complete(client, app, policy_on):
    """PRODUCTION 팀이 제작 시작/완료 가능 — P0-9 권한 역전 수정(200 성공)."""
    _login(client, _make_user("prod-user", role="STAFF", team="PRODUCTION"))

    start_id = _make_order("CONFIRM")
    r1 = client.post(f"/api/orders/{start_id}/production/start", json={})
    assert r1.status_code == 200 and r1.get_json()["success"] is True, r1.get_data(as_text=True)

    done_id = _make_order("PRODUCTION")
    r2 = client.post(f"/api/orders/{done_id}/production/complete", json={})
    assert r2.status_code == 200 and r2.get_json()["success"] is True, r2.get_data(as_text=True)


def test_production_denied_for_unrelated_team(client, app, policy_on):
    """DRAWING 팀은 production start 403(생산 정책 팀 밖)."""
    _login(client, _make_user("draw-onprod", role="STAFF", team="DRAWING"))
    oid = _make_order("CONFIRM")
    resp = client.post(f"/api/orders/{oid}/production/start", json={})
    assert _denied(resp), (resp.status_code, resp.headers.get("X-Auth-Policy"))


# --------------------------------------------------------------------------
# drawing/construction: ASSIGNMENT-00 user-ID row 기반
# --------------------------------------------------------------------------
def test_drawing_assigned_id_allows_only_assignee(client, app, policy_on):
    """DRAWING 배정된 user 만 통과, 미배정 DRAWING 팀원은 403 (ID-row 기반)."""
    assignee = _make_user("draw-x", role="STAFF", team="DRAWING")
    other = _make_user("draw-y", role="STAFF", team="DRAWING")
    assignee_creds, other_creds = _creds(assignee), _creds(other)
    oid = _make_order("DRAWING")
    _assign(oid, "DRAWING", assignee_creds[0])

    _login(client, other_creds)
    denied = client.post(f"/api/orders/{oid}/transfer-drawing", json={})
    assert _denied(denied), (denied.status_code, denied.headers.get("X-Auth-Policy"))

    _login(client, assignee_creds)
    allowed = client.post(f"/api/orders/{oid}/transfer-drawing", json={})
    assert _gate_passed(allowed), allowed.headers.get("X-Auth-Policy")


def test_drawing_team_fallback_when_no_assignment(client, app, policy_on):
    """배정 row 가 없으면(backfill 미완) DRAWING 팀원은 team 폴백으로 통과 — lock-out 방지."""
    user = _make_user("draw-fallback", role="STAFF", team="DRAWING")
    oid = _make_order("DRAWING")  # 배정 없음
    _login(client, user)
    resp = client.post(f"/api/orders/{oid}/transfer-drawing", json={})
    assert _gate_passed(resp), resp.headers.get("X-Auth-Policy")


def test_construction_assigned_id_allows_only_assignee(client, app, policy_on):
    """CONSTRUCTION 배정된 user 만 construction start 통과, 미배정은 403."""
    assignee = _make_user("con-x", role="STAFF", team="CONSTRUCTION")
    other = _make_user("con-y", role="STAFF", team="CONSTRUCTION")
    assignee_creds, other_creds = _creds(assignee), _creds(other)
    oid = _make_order("CONSTRUCTION")
    _assign(oid, "CONSTRUCTION", assignee_creds[0])

    _login(client, other_creds)
    assert _denied(client.post(f"/api/orders/{oid}/construction/start", json={}))

    _login(client, assignee_creds)
    assert _gate_passed(client.post(f"/api/orders/{oid}/construction/start", json={}))


def test_measure_team_normalized_to_sales(client, app, policy_on):
    """team=MEASURE 는 SALES 로 정규화되어 ERP_EDIT command 통과(§2.1 (a)/(b))."""
    _login(client, _make_user("measure-user", role="STAFF", team="MEASURE"))
    oid = _make_order()
    resp = client.post(f"/api/orders/{oid}/call-log", json={"result": "connected"})
    assert _gate_passed(resp), resp.headers.get("X-Auth-Policy")


# --------------------------------------------------------------------------
# /api·/erp/api 권한 실패 = 403 JSON (redirect 0 — P1-13/P1-18)
# --------------------------------------------------------------------------
def test_erp_api_namespace_denies_with_json_not_redirect(client, app, policy_on):
    """/erp/api 권한 실패는 302 redirect 가 아니라 403 JSON (P1-18 JSON parser 파손 수정)."""
    _login(client, _make_user("viewer-erpapi", role="VIEWER"))
    resp = client.post("/erp/api/notifications/send", json={"message": "x"})
    assert resp.status_code == 403
    assert "Location" not in resp.headers
    assert resp.is_json and resp.get_json()["success"] is False


def test_api_namespace_denies_with_json_not_redirect(client, app, policy_on):
    """/api 권한 실패는 403 JSON (P1-13)."""
    _login(client, _make_user("staff-master", role="STAFF", team="CS"))
    # WDC master 는 ADMIN/MANAGER 전용 → STAFF/CS 는 403 JSON
    resp = client.post("/api/wdcalculator/products", json={"name": "x"})
    assert resp.status_code == 403
    assert "Location" not in resp.headers
    assert resp.is_json


# --------------------------------------------------------------------------
# 정상 role 회귀 0
# --------------------------------------------------------------------------
def test_normal_roles_pass_gate(client, app, policy_on):
    """CS/SALES/ADMIN/MANAGER 정상 업무는 정책 가드를 통과(회귀 0)."""
    oid = _make_order()

    _login(client, _make_user("cs-fin", role="STAFF", team="CS"))
    assert _gate_passed(client.post(f"/api/orders/{oid}/settlement/issue", json={}))

    _login(client, _make_user("sales-struct", role="STAFF", team="SALES"))
    assert _gate_passed(client.put(f"/api/orders/{oid}/structured", json={}))

    _login(client, _make_user("admin-master", role="ADMIN"))
    assert _gate_passed(client.post("/api/wdcalculator/products", json={"name": "x"}))

    _login(client, _make_user("manager-bulk", role="MANAGER"))
    assert _gate_passed(client.post("/bulk_action", data={"action": "x"}))


def test_master_mutation_denies_staff_allows_manager(client, app, policy_on):
    """WDC master 는 STAFF 403, MANAGER/ADMIN 통과(WDC-AUTH-01 master MANAGER+)."""
    _login(client, _make_user("staff-nomaster", role="STAFF", team="SALES"))
    assert _denied(client.post("/api/wdcalculator/products", json={"name": "x"}))

    _login(client, _make_user("mgr-master", role="MANAGER"))
    assert _gate_passed(client.post("/api/wdcalculator/products", json={"name": "x"}))


# --------------------------------------------------------------------------
# 가드 OFF 기본값에서는 무회귀 (기존 테스트 영향 0 증명)
# --------------------------------------------------------------------------
def test_policy_inactive_by_default_under_testing(client, app):
    """AUTH_POLICY_ENABLED 미지정 + TESTING → 가드 OFF, VIEWER 도 정책 차단 없음(회귀 0)."""
    app.config.pop("AUTH_POLICY_ENABLED", None)
    _login(client, _make_user("viewer-off", role="VIEWER"))
    oid = _make_order("COMPLETED")
    resp = client.post(f"/api/orders/{oid}/settlement/issue", json={})
    assert resp.headers.get("X-Auth-Policy") is None  # 가드 미개입
