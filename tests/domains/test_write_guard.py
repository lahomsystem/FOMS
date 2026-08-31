"""WRITE-GUARD-01: 공용 CSRF+Origin write guard 계약 테스트.

가드는 ``WRITE_GUARD_ENABLED`` config(미지정 시 ``not TESTING``)로 켜진다. 기존 테스트는
``TESTING=True`` + 미지정이라 토큰 없이 통과하고(회귀 0), 이 파일만 ``guard_on`` 픽스처로
명시 활성화한 뒤 원복한다(cross-test 오염 방지).

앱 요청 teardown 이 세션을 close → 요청 후에는 정수 id 로 재조회해 검증한다
(test_call_log_api 패턴 준용).
"""

import os

import pytest
from itsdangerous import URLSafeSerializer
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User
from foms.services.request_write_guard import (
    _CSRF_SALT,
    _CSRF_SESSION_KEY,
    load_write_guard_manifest,
)

_MUTATION_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼
# --------------------------------------------------------------------------
@pytest.fixture
def guard_on(app):
    """이 테스트 동안만 공용 write guard 를 강제 활성화하고 원복한다."""
    sentinel = object()
    prev = app.config.get("WRITE_GUARD_ENABLED", sentinel)
    app.config["WRITE_GUARD_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("WRITE_GUARD_ENABLED", None)
    else:
        app.config["WRITE_GUARD_ENABLED"] = prev


def _login(client, *, username="cs-user", role="STAFF", team="CS"):
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


def _issue_csrf(client, app):
    """클라이언트 세션에 CSRF seed 를 심고, 서버가 인정할 서명 토큰을 반환한다.

    서버 검증(_serializer + 세션 seed 비교)과 동일한 방식으로 토큰을 만든다.
    """
    seed = os.urandom(16).hex()
    with client.session_transaction() as sess:
        sess[_CSRF_SESSION_KEY] = seed
    return URLSafeSerializer(app.secret_key, salt=_CSRF_SALT).dumps(seed)


def _create_order():
    order = Order(
        received_date="2026-04-07",
        customer_name="가드 대상",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        status="RECEIVED",
        manager_name="Alice",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "RECEIVED"}},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _fresh_order(oid):
    db_session.remove()
    return db_session.query(Order).filter_by(id=oid).first()


def _is_write_guard_block(resp):
    return resp.status_code == 403 and resp.headers.get("X-Write-Guard") == "blocked"


# --------------------------------------------------------------------------
# static gate: 모든 mutation route 가 manifest 에 등재되어야 한다
# --------------------------------------------------------------------------
def test_manifest_covers_every_mutation_route(app):
    """url_map 의 모든 POST/PUT/PATCH/DELETE endpoint 가 manifest 에 등재(누락=fail)."""
    manifest = load_write_guard_manifest()
    routes = manifest.get("routes", {})

    # 실 FOMS mutation route 는 전부 blueprint-scoped(dotted)다 — app.py 직접 라우트 추가
    # 금지 규칙상 app-level 라우트(favicon/build_info)는 GET 뿐이다. 공유 test app 싱글턴에
    # 다른 테스트가 add_url_rule 로 주입하는 내부 라우트(예: limit_read_body)는 non-dotted
    # 이므로 여기서 제외해 오탐을 막는다.
    url_map_endpoints = set()
    for rule in app.url_map.iter_rules():
        if (set(rule.methods or ()) & _MUTATION_METHODS) and "." in rule.endpoint:
            url_map_endpoints.add(rule.endpoint)

    manifest_endpoints = set(routes.keys())

    missing = sorted(url_map_endpoints - manifest_endpoints)
    stale = sorted(manifest_endpoints - url_map_endpoints)
    assert not missing, f"manifest 미등재 mutation route(=static fail): {missing}"
    assert not stale, f"manifest 에만 있고 url_map 에 없는 stale route: {stale}"

    for ep, meta in routes.items():
        assert meta.get("mode") in ("guard", "exempt"), ep
        if meta["mode"] == "exempt":
            assert meta.get("reason"), f"exempt route 사유 누락: {ep}"


# --------------------------------------------------------------------------
# guarded route: 토큰/Origin 검증
# --------------------------------------------------------------------------
def test_missing_csrf_blocked_with_no_db_change(client, app, guard_on):
    """유효 CSRF 없는 cookie-auth mutation → 403(X-Write-Guard) + DB 변화 0."""
    _login(client)
    oid = _create_order()

    resp = client.post(f"/api/orders/{oid}/call-log", json={"result": "connected"})

    assert _is_write_guard_block(resp), (resp.status_code, resp.headers.get("X-Write-Guard"))
    refreshed = _fresh_order(oid)
    assert "calls" not in (refreshed.structured_data or {})  # 핸들러 실행 전 차단 → DB0


def test_valid_csrf_same_origin_passes(client, app, guard_on):
    """유효 CSRF + same-origin → 정상 통과(200), 기존 기능 유지."""
    _login(client)
    oid = _create_order()
    token = _issue_csrf(client, app)

    resp = client.post(
        f"/api/orders/{oid}/call-log",
        json={"result": "connected", "memo": "확인"},
        headers={"X-CSRF-Token": token},
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.headers.get("X-Write-Guard") is None
    refreshed = _fresh_order(oid)
    assert refreshed.structured_data["calls"][0]["result"] == "connected"


def test_cross_origin_blocked_even_with_token(client, app, guard_on):
    """유효 토큰이라도 cross-origin Origin → 403 + DB0."""
    _login(client)
    oid = _create_order()
    token = _issue_csrf(client, app)

    resp = client.post(
        f"/api/orders/{oid}/call-log",
        json={"result": "connected"},
        headers={"X-CSRF-Token": token, "Origin": "https://evil.example"},
    )

    assert _is_write_guard_block(resp)
    refreshed = _fresh_order(oid)
    assert "calls" not in (refreshed.structured_data or {})


def test_csrf_token_via_json_body_for_beacon(client, app, guard_on):
    """sendBeacon 대체: JSON body 의 csrf_token 도 헤더처럼 인정된다."""
    _login(client)
    oid = _create_order()
    token = _issue_csrf(client, app)

    resp = client.post(
        f"/api/orders/{oid}/call-log",
        json={"result": "connected", "csrf_token": token},
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)
    assert resp.headers.get("X-Write-Guard") is None


# --------------------------------------------------------------------------
# exempt routes: 자기 정책대로 동작(CSRF 403 아님)
# --------------------------------------------------------------------------
def test_exempt_rum_ingest_not_blocked(client, app, guard_on):
    """anonymous RUM ingest 는 CSRF 없이도 통과(exempt)."""
    resp = client.post("/api/foms/rum", json={"metric": "LCP", "value": 1200})
    assert resp.status_code == 200
    assert resp.headers.get("X-Write-Guard") is None


def test_exempt_webhook_not_blocked_by_csrf(client, app, guard_on):
    """provider webhook 은 write-guard 가 아니라 서명 정책으로 판정(401), CSRF 403 아님."""
    resp = client.post("/api/channel/webhooks", json={"event": "x"})
    assert resp.headers.get("X-Write-Guard") is None
    assert resp.status_code != 403  # 서명 미들웨어(401)로 판정, write-guard 차단 아님


def test_exempt_login_not_blocked_by_csrf(client, app, guard_on):
    """login 은 anonymous(pre-session) → exempt, CSRF 없이도 write-guard 통과."""
    resp = client.post("/login", data={"username": "", "password": ""})
    assert resp.headers.get("X-Write-Guard") is None
    assert resp.status_code == 200  # 자격 미달 → 로그인 폼 재렌더(차단 아님)


# --------------------------------------------------------------------------
# logout/switch: POST 전용, GET 405
# --------------------------------------------------------------------------
def test_logout_get_returns_405(client):
    assert client.get("/logout").status_code == 405


def test_switch_back_get_returns_405(client):
    assert client.get("/switch-back").status_code == 405


def test_switch_user_get_returns_405(client):
    assert client.get("/switch-user/1").status_code == 405


# --------------------------------------------------------------------------
# 회귀 방어: 기본(TESTING) 에서는 가드 비활성 → 기존 테스트 무영향
# --------------------------------------------------------------------------
def test_guard_inactive_by_default_under_testing(client, app):
    """WRITE_GUARD_ENABLED 미지정 + TESTING → 토큰 없이도 통과(기존 mutation 회귀 0)."""
    app.config.pop("WRITE_GUARD_ENABLED", None)
    _login(client)
    oid = _create_order()

    resp = client.post(f"/api/orders/{oid}/call-log", json={"result": "connected"})

    assert resp.status_code == 200
    assert resp.headers.get("X-Write-Guard") is None


# --------------------------------------------------------------------------
# 회귀 고정: standalone 문서(/map_view)도 CSRF 배선을 갖는다
#
# 운영 사고 2026-08-31 — map_view.html 이 layout_head 를 쓰지 않아 토큰/래퍼가 통째로
# 빠져 있었고, ADMIN 계정의 주소 수정이 403 invalid_csrf_token 으로 막혔다.
# (security_logs: uid 38 upperkill, erp_map.api_update_order_address)
# --------------------------------------------------------------------------
def _extract_csrf_meta(html: str) -> str:
    """렌더된 페이지에서 ``<meta name="csrf-token">`` 값을 뽑는다."""
    import re

    m = re.search(r'<meta name="csrf-token" content="([^"]+)">', html)
    assert m, "렌더된 페이지에 csrf-token meta 가 없다"
    return m.group(1)


def test_map_view_page_serves_csrf_token(client, app, guard_on):
    """/map_view 가 토큰 meta 와 fetch 자동 부착 래퍼를 함께 서빙한다."""
    _login(client)

    resp = client.get("/map_view")

    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert _extract_csrf_meta(html)
    assert "window.__FOMS_CSRF_BOUND" in html
    assert "X-CSRF-Token" in html


def test_update_address_passes_guard_with_token_from_map_view(client, app, guard_on):
    """/map_view 가 준 토큰으로 주소 수정 POST 가 write guard 를 통과한다."""
    _login(client)
    oid = _create_order()

    page = client.get("/map_view")
    token = _extract_csrf_meta(page.get_data(as_text=True))

    resp = client.post(
        f"/api/orders/{oid}/update_address",
        json={"address": "경기 오산시 가수동 449"},
        headers={"X-CSRF-Token": token},
    )

    assert resp.headers.get("X-Write-Guard") is None, "가드가 여전히 차단한다"
    assert resp.status_code != 403


def test_update_address_without_token_is_still_blocked(client, app, guard_on):
    """음성 대조군: 토큰이 없으면 여전히 403 이어야 한다(가드가 무력화되지 않았다)."""
    _login(client)
    oid = _create_order()

    resp = client.post(f"/api/orders/{oid}/update_address", json={"address": "서울"})

    assert resp.status_code == 403
    assert resp.headers.get("X-Write-Guard") == "blocked"
