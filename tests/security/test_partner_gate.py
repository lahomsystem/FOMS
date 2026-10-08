"""PARTNER-01: 외부 협력사 계정 문지기 · 주문 조회 범위 계약.

스펙 docs/specs/2026-10-08-partner-portal_SPEC.md §4 · §10 (1단계).

* 문지기(래칫): ``app.url_map`` 의 **모든** 규칙을 협력사 세션으로 부른다. 허용 목록 밖은
  전부 문지기 응답(API 403 JSON · 화면 403 막힘 화면)이어야 한다. 새 라우트는 자동으로 검사된다.
* 허용 목록 안의 파일 관문은 주문 단위로 다시 판정한다 — 자기 협력사 주문만 열리고, 다른 협력사 ·
  우리 주문은 403(음성 대조군 포함).
* ``user_can_read_order``: 협력사는 자기 협력사 주문만. 우리 직원은 지금처럼 전역 조회(대조군).
* 꺼진 협력사 계정은 세션이 끊긴다. Socket.IO 연결 거부. 넓은 알림 경로에서 협력사 제외.
* DB 제약: 협력사 role ↔ 협력사 id 짝.
"""
from __future__ import annotations

import itertools

import pytest
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

import foms.api.files.routes as file_routes
from db import db_session
from foms.services.auth.partner_scope import PARTNER_ALLOWED_ENDPOINTS
from foms.services.notifications.recipients import resolve_recipients_for_notification
from foms.services.orders.order_mutation_policy import user_can_read_order
from models import Notification, Order, PartnerOrg, User

_counter = itertools.count(1)
_R2_HOST = "https://account.r2.cloudflarestorage.com/"
_DENIED_MSG = "협력사 계정으로는 이 화면을 쓸 수 없습니다."


class _FakeR2Storage:
    storage_type = "r2"

    def get_download_url(self, storage_key, expires_in=3600, response_content_disposition=None):
        return f"{_R2_HOST}{storage_key}?X-Amz-Signature=fresh"


@pytest.fixture
def r2_storage(monkeypatch):
    monkeypatch.setattr(file_routes, "get_storage", lambda: _FakeR2Storage())


def _org(name: str, *, is_active: bool = True) -> PartnerOrg:
    org = PartnerOrg(name=name, is_active=is_active)
    db_session.add(org)
    db_session.commit()
    return org


def _user(*, role: str = "STAFF", team: str | None = "CS", org: PartnerOrg | None = None,
          password: str = "x", name: str | None = None) -> User:
    n = next(_counter)
    user = User(
        username=f"partner-gate-{n}",
        password=password,
        role=role,
        team=team,
        name=name or f"user-{n}",
        partner_org_id=org.id if org else None,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _order(org: PartnerOrg | None = None) -> Order:
    order = Order(
        received_date="2026-10-08",
        customer_name="고객",
        phone="010-0000-0000",
        address="addr",
        product="p",
        status="RECEIVED",
        partner_org_id=org.id if org else None,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _client(app, user: User | None):
    client = app.test_client()
    if user is not None:
        with client.session_transaction() as sess:
            sess["user_id"] = user.id
    return client


@pytest.fixture
def world(app):
    """협력사 A·B, 협력사 A 계정, 우리 직원, 주문 3건(A·B·우리)."""
    org_a = _org("협력사A")
    org_b = _org("협력사B")
    world = {
        "org_a": org_a,
        "org_b": org_b,
        "partner": _user(role="PARTNER", team=None, org=org_a),
        "staff": _user(),
        "order_a": _order(org_a),
        "order_b": _order(org_b),
        "order_ours": _order(None),
    }
    return {k: v.id for k, v in world.items()}


def _sample_path(rule, order_id: int) -> str:
    """규칙에 맞는 임의 URL. 정수 인자는 **우리 주문** id(협력사가 못 봐야 하는 행)."""
    values = {}
    for arg, conv in rule._converters.items():
        kind = type(conv).__name__
        if kind == "IntegerConverter":
            values[arg] = order_id
        elif kind == "PathConverter":
            values[arg] = f"orders/{order_id}/attachments/x.jpg"
        else:
            values[arg] = "x"
    return rule.build(values, append_unknown=False)[1]


# --------------------------------------------------------------------------
# 문지기 래칫 — 모든 규칙
# --------------------------------------------------------------------------
def test_every_rule_outside_allowlist_is_blocked_for_partner(app, world):
    client = _client(app, db_session.get(User, world["partner"]))
    checked = 0
    leaks = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint in PARTNER_ALLOWED_ENDPOINTS:
            continue
        path = _sample_path(rule, world["order_ours"])
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            resp = client.open(path, method=method)
            checked += 1
            if "/api/" in path or method != "GET":
                # API · 쓰기: 403 JSON(문지기 문구)
                body = resp.get_json(silent=True) or {}
                if resp.status_code != 403 or body.get("error") != _DENIED_MSG:
                    leaks.append((rule.endpoint, method, path, resp.status_code))
            elif resp.status_code != 302 or not resp.headers.get("Location", "").endswith("/partner"):
                # 화면: 협력사 첫 화면으로 보낸다
                leaks.append((rule.endpoint, method, path, resp.status_code))
    assert checked > 300, checked
    assert leaks == [], leaks[:20]


def test_internal_staff_is_not_gated(app, world):
    """대조군: 우리 직원은 문지기를 지나 원래 화면을 받는다."""
    client = _client(app, db_session.get(User, world["staff"]))
    resp = client.get("/")
    assert resp.status_code != 403
    assert not resp.headers.get("Location", "").endswith("/partner")


def test_logged_in_partner_is_sent_to_portal_and_can_logout(app, world):
    client = _client(app, db_session.get(User, world["partner"]))
    resp = client.get("/login")
    assert resp.status_code == 302 and resp.headers["Location"].endswith("/partner")

    home = client.get("/partner")
    html = home.get_data(as_text=True)
    assert home.status_code == 200 and "협력사A" in html and "로그아웃" in html

    out = client.post("/logout")
    assert out.status_code == 302
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_partner_password_login_lands_on_portal(app):
    org = _org("협력사로그인")
    user = _user(role="PARTNER", team=None, org=org, password=generate_password_hash("pw-1234!"))
    client = app.test_client()
    resp = client.post("/login", data={"username": user.username, "password": "pw-1234!"},
                       follow_redirects=True)
    assert resp.status_code == 200
    assert "주문 목록" in resp.get_data(as_text=True)


@pytest.fixture
def policy_on(app):
    """운영처럼 쓰기 정책 엔진(AUTH-01)을 켠다(테스트 기본은 꺼짐)."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


def test_partner_can_logout_with_policy_engine_on(app, world, policy_on):
    """운영에서는 쓰기 정책 엔진이 켜져 있다 — 협력사 로그아웃이 거기서 막히면 안 된다."""
    client = _client(app, db_session.get(User, world["partner"]))
    resp = client.post("/logout")
    assert resp.status_code == 302
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_policy_engine_denies_partner_outside_account_policies(app):
    from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy

    org = _org("협력사정책")
    partner = _user(role="PARTNER", team=None, org=org)
    allowed = {pid for pid, pol in POLICY_REGISTRY.items() if evaluate_policy(pol, partner).allowed}
    assert allowed == {"ACCOUNT_SELF", "ACCOUNT_ANON", "PARTNER_PORTAL"}


# --------------------------------------------------------------------------
# 허용 목록 안 — 파일 관문은 주문 단위로 다시 판정
# --------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ["view", "download", "presigned-urls"])
def test_file_gate_opens_only_own_partner_orders(app, world, r2_storage, kind):
    client = _client(app, db_session.get(User, world["partner"]))

    def call(order_id):
        return client.get(f"/api/files/{kind}/orders/{order_id}/attachments/x.jpg")

    own = call(world["order_a"])
    assert own.status_code in (200, 302), own.status_code
    assert call(world["order_b"]).status_code == 403
    assert call(world["order_ours"]).status_code == 403


def test_file_gate_staff_still_reads_partner_orders(app, world, r2_storage):
    """대조군: 우리 직원은 협력사 주문 파일도 지금처럼 연다."""
    client = _client(app, db_session.get(User, world["staff"]))
    resp = client.get(f"/api/files/presigned-urls/orders/{world['order_a']}/attachments/x.jpg")
    assert resp.status_code == 200


# --------------------------------------------------------------------------
# user_can_read_order
# --------------------------------------------------------------------------
def test_read_scope_partner_only_own_org(app, world):
    partner = db_session.get(User, world["partner"])
    assert user_can_read_order(partner, db_session.get(Order, world["order_a"])) is True
    assert user_can_read_order(partner, db_session.get(Order, world["order_b"])) is False
    assert user_can_read_order(partner, db_session.get(Order, world["order_ours"])) is False
    assert user_can_read_order(partner, None) is False


def test_read_scope_staff_unchanged(app, world):
    staff = db_session.get(User, world["staff"])
    for key in ("order_a", "order_b", "order_ours"):
        assert user_can_read_order(staff, db_session.get(Order, world[key])) is True


# --------------------------------------------------------------------------
# 꺼진 협력사
# --------------------------------------------------------------------------
def test_inactive_org_drops_session(app, world):
    org = db_session.get(PartnerOrg, world["org_a"])
    org.is_active = False
    db_session.commit()
    client = _client(app, db_session.get(User, world["partner"]))

    page = client.get("/")
    assert page.status_code == 302 and "/login" in page.headers["Location"]
    with client.session_transaction() as sess:
        assert "user_id" not in sess

    client = _client(app, db_session.get(User, world["partner"]))
    api = client.get(f"/api/files/presigned-urls/orders/{world['order_a']}/attachments/x.jpg")
    assert api.status_code == 401


# --------------------------------------------------------------------------
# 문지기가 닿지 않는 길
# --------------------------------------------------------------------------
def test_socketio_refuses_partner_and_accepts_staff(app, world):
    from app import socketio

    partner_http = _client(app, db_session.get(User, world["partner"]))
    partner_ws = socketio.test_client(app, flask_test_client=partner_http)
    assert partner_ws.is_connected() is False

    staff_http = _client(app, db_session.get(User, world["staff"]))
    staff_ws = socketio.test_client(app, flask_test_client=staff_http)
    try:
        assert staff_ws.is_connected() is True
    finally:
        staff_ws.disconnect()


def test_broad_notifications_skip_partner(app, world):
    partner = db_session.get(User, world["partner"])
    # 이름이 우리 담당자와 같아도 담당자 이름 경로로 새지 않는다.
    partner.name = "동명이인"
    db_session.commit()
    staff = db_session.get(User, world["staff"])
    for kwargs in (
        {"target_type": "ALL"},
        {"target_type": "ROLE", "target_role": "PARTNER"},
        {"target_type": "ORDER", "target_manager_name": "동명이인"},
    ):
        note = Notification(notification_type="TEST", title="t", **kwargs)
        ids = {uid for uid, _src in resolve_recipients_for_notification(db_session, note)}
        assert world["partner"] not in ids, kwargs
    all_note = Notification(notification_type="TEST", title="t", target_type="ALL")
    assert staff.id in {uid for uid, _ in resolve_recipients_for_notification(db_session, all_note)}

    direct = Notification(notification_type="TEST", title="t", target_type="USER",
                          target_user_id=world["partner"])
    assert world["partner"] in {uid for uid, _ in resolve_recipients_for_notification(db_session, direct)}


# --------------------------------------------------------------------------
# DB 제약
# --------------------------------------------------------------------------
def test_partner_role_requires_org(app):
    db_session.add(User(username="no-org-partner", password="x", name="n", role="PARTNER"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_internal_user_cannot_have_org(app):
    org = _org("협력사제약")
    db_session.add(User(username="staff-with-org", password="x", name="n", role="STAFF",
                        partner_org_id=org.id))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
