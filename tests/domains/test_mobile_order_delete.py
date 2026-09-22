"""MOBILE-DELETE-01 — 모바일 주문 삭제(휴지통)·되돌리기 API + 상세 페이지 노출 계약.

권한은 ORDER_SOFT_DELETE 정책(ADMIN/MANAGER 또는 STAFF+CS/SALES/MEASURE) 을 따르고,
단계 가드(free/warn/blocked) 는 서버가 강제하며 UI 는 같은 값을 data-* 로 받는다.
"""

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User
from foms.api.orders.mobile_delete import (
    GUARD_BLOCKED,
    GUARD_FREE,
    GUARD_WARN,
    stage_guard_for_order,
)
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, load_policy_manifest


@pytest.fixture
def policy_on(app):
    prev = app.config.get("AUTH_POLICY_ENABLED")
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is None:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


def _make_user(username, *, role="STAFF", team=None):
    user = User(
        username=username, password=generate_password_hash("pw"), role=role, team=team,
        name=f"{username}-name", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return (user.id, user.username, user.role)


def _login(client, creds):
    uid, username, role = creds
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = username
        sess["role"] = role


def _make_order(stage="RECEIVED", *, status=None):
    order = Order(
        received_date="2026-09-22", customer_name="모바일 삭제 대상", phone="010-0000-0000",
        address="Seoul", product="Wardrobe", status=status or stage, erp_stage_code=stage,
        is_erp_order=True,
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _delete(client, order_id, **body):
    return client.post(f"/api/orders/{order_id}/mobile-delete", json=body)


# ----------------------------------------------------------------- 정책 등록
def test_policy_registered_and_routes_in_manifest():
    policy = POLICY_REGISTRY["ORDER_SOFT_DELETE"]
    assert set(policy.teams) == {"CS", "SALES"}
    assert policy.manager_ok is True and policy.viewer is False
    routes = load_policy_manifest()["routes"]
    for ep in ("orders.mobile_delete_order", "orders.mobile_restore_order"):
        assert routes[ep]["policy_id"] == "ORDER_SOFT_DELETE", ep


# ----------------------------------------------------------------- 권한
@pytest.mark.parametrize("role,team", [
    ("ADMIN", None), ("MANAGER", None), ("STAFF", "CS"), ("STAFF", "SALES"), ("STAFF", "MEASURE"),
])
def test_allowed_roles_can_delete(client, app, policy_on, role, team):
    _login(client, _make_user(f"ok-{role}-{team}", role=role, team=team))
    order_id = _make_order("RECEIVED")
    resp = _delete(client, order_id, reason_code="customer_request")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is True and body["data"]["order_id"] == order_id
    assert body["data"]["undo_seconds"] == 5
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    assert order.deleted_at is not None
    # PC 단건 삭제와 같이 status 는 덮지 않는다(canonical deleted_at 만).
    assert order.status == "RECEIVED" and order.original_status is None


@pytest.mark.parametrize("role,team", [
    ("STAFF", "DRAWING"), ("STAFF", "PRODUCTION"), ("STAFF", "CONSTRUCTION"), ("VIEWER", "CS"),
])
def test_other_teams_and_viewer_denied(client, app, policy_on, role, team):
    _login(client, _make_user(f"no-{role}-{team}", role=role, team=team))
    order_id = _make_order("RECEIVED")
    resp = _delete(client, order_id, reason_code="customer_request")
    assert resp.status_code == 403, resp.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.get(Order, order_id).deleted_at is None


# ----------------------------------------------------------------- 단계 가드
@pytest.mark.parametrize("stage,level", [
    ("RECEIVED", GUARD_FREE), ("MEASURE", GUARD_FREE), ("DRAWING", GUARD_FREE),
    ("CONFIRM", GUARD_WARN), ("PRODUCTION", GUARD_WARN), ("CONSTRUCTION", GUARD_WARN),
    ("CS", GUARD_BLOCKED), ("COMPLETED", GUARD_BLOCKED),
])
def test_stage_guard_levels(stage, level):
    class _O:
        erp_stage_code = stage
        status = stage
    assert stage_guard_for_order(_O())["level"] == level


def test_stage_guard_falls_back_to_status_when_stage_code_missing():
    class _O:
        erp_stage_code = None
        status = "AS_RECEIVED"
    assert stage_guard_for_order(_O())["level"] == GUARD_BLOCKED


def test_free_stage_allows_missing_reason(client, app, policy_on):
    _login(client, _make_user("free-user", role="STAFF", team="CS"))
    order_id = _make_order("MEASURE")
    resp = _delete(client, order_id)
    assert resp.status_code == 200, resp.get_data(as_text=True)


def test_warn_stage_requires_reason(client, app, policy_on):
    _login(client, _make_user("warn-user", role="STAFF", team="SALES"))
    order_id = _make_order("PRODUCTION")
    resp = _delete(client, order_id)
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "REASON_REQUIRED"
    ok = _delete(client, order_id, reason_code="input_correction")
    assert ok.status_code == 200, ok.get_data(as_text=True)


def test_blocked_stage_returns_409(client, app, policy_on):
    _login(client, _make_user("blocked-admin", role="ADMIN"))
    order_id = _make_order("COMPLETED")
    resp = _delete(client, order_id, reason_code="customer_request")
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "MOBILE_DELETE_BLOCKED"
    db_session.expire_all()
    assert db_session.get(Order, order_id).deleted_at is None


# ----------------------------------------------------------------- 사유
def test_other_reason_requires_note(client, app, policy_on):
    _login(client, _make_user("other-user", role="STAFF", team="CS"))
    order_id = _make_order("RECEIVED")
    resp = _delete(client, order_id, reason_code="other", reason_note="  ")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "REASON_NOTE_REQUIRED"
    ok = _delete(client, order_id, reason_code="other", reason_note="네이버 중복 주문")
    assert ok.status_code == 200, ok.get_data(as_text=True)


def test_unknown_reason_code_rejected(client, app, policy_on):
    _login(client, _make_user("bad-reason", role="ADMIN"))
    order_id = _make_order("RECEIVED")
    resp = _delete(client, order_id, reason_code="duplicate")
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "REASON_INVALID"


# ----------------------------------------------------------------- 버전·이벤트·복원
def test_version_conflict_409(client, app, policy_on):
    _login(client, _make_user("ver-user", role="ADMIN"))
    order_id = _make_order("RECEIVED")
    resp = _delete(client, order_id, reason_code="customer_request", mutation_version=999)
    assert resp.status_code == 409, resp.get_data(as_text=True)
    assert resp.get_json()["code"] == "REVISION_CONFLICT"
    db_session.expire_all()
    assert db_session.get(Order, order_id).deleted_at is None


def test_delete_records_event_and_restore_clears(client, app, policy_on):
    _login(client, _make_user("evt-user", role="STAFF", team="CS"))
    order_id = _make_order("DRAWING")
    resp = _delete(client, order_id, reason_code="customer_request")
    assert resp.status_code == 200, resp.get_data(as_text=True)
    db_session.expire_all()
    events = db_session.query(OrderEvent).filter(OrderEvent.order_id == order_id).all()
    assert any(e.event_type == "ORDER_SOFT_DELETED" for e in events)

    # 삭제된 주문은 다시 삭제 불가(404) — active_filter.
    again = _delete(client, order_id, reason_code="customer_request")
    assert again.status_code == 404

    restore = client.post(f"/api/orders/{order_id}/mobile-restore", json={})
    assert restore.status_code == 200, restore.get_data(as_text=True)
    db_session.expire_all()
    order = db_session.get(Order, order_id)
    assert order.deleted_at is None
    assert order.status == "DRAWING" and order.original_status is None

    # 휴지통에 없는 주문 되돌리기는 404.
    again = client.post(f"/api/orders/{order_id}/mobile-restore", json={})
    assert again.status_code == 404


def test_restore_refuses_legacy_status_mirrored_order(client, app, policy_on):
    """PC bulk 삭제처럼 status='DELETED' 로 덮인 주문은 모바일 되돌리기 대상이 아니다(409)."""
    _login(client, _make_user("legacy-admin", role="ADMIN"))
    order_id = _make_order("RECEIVED")
    order = db_session.get(Order, order_id)
    order.original_status = "RECEIVED"
    order.status = "DELETED"
    order.deleted_at = "2026-09-22 00:00:00"
    db_session.commit()
    resp = client.post(f"/api/orders/{order_id}/mobile-restore", json={})
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "LEGACY_DELETED"


def test_restore_denied_for_other_team(client, app, policy_on):
    _login(client, _make_user("del-admin", role="ADMIN"))
    order_id = _make_order("RECEIVED")
    assert _delete(client, order_id, reason_code="customer_request").status_code == 200
    _login(client, _make_user("restore-drawing", role="STAFF", team="DRAWING"))
    resp = client.post(f"/api/orders/{order_id}/mobile-restore", json={})
    assert resp.status_code == 403


# ----------------------------------------------------------------- 상세 페이지 노출
def _detail(client, order_id):
    return client.get(f"/erp/orders/{order_id}/mobile", headers={
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile Safari/604.1",
    })


def test_detail_page_exposes_root_only_for_allowed_user(client, app, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    order_id = _make_order("PRODUCTION")
    cs = _make_user("page-cs", role="STAFF", team="CS")
    drawing = _make_user("page-drawing", role="STAFF", team="DRAWING")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", f"{cs[0]},{drawing[0]}")
    _login(client, cs)
    html = _detail(client, order_id).get_data(as_text=True)
    assert 'id="foms-mobile-delete-root"' in html
    assert 'data-guard-level="warn"' in html
    assert f'data-order-id="{order_id}"' in html
    assert 'data-foms-more-open' in html
    assert 'id="foms-mdel-confirm-tpl"' in html
    assert 'data-mdel-reason="other"' in html

    _login(client, drawing)
    html2 = _detail(client, order_id).get_data(as_text=True)
    assert 'foms-mobile-delete-root' not in html2
    assert 'data-foms-more-open' not in html2
    assert 'foms-mdel-confirm-tpl' not in html2
