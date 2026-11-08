"""FCOMM-01 3단계 겹 1: 프리랜서 영업 계정 기본 거부 문지기 계약.

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.3 겹 1 · §6.5 (플랜 T14).

* 래칫: ``app.url_map`` 의 **모든** 규칙을 켜진 프리랜서 세션으로 부른다. 허용 목록 밖(또는 허용했지만
  막은 방법)은 전부 문지기 응답이어야 한다 — API · 쓰기는 403 JSON(문지기 문구), 화면은 프리랜서 홈으로 302.
  새 라우트는 자동으로 검사된다. 빼는 규칙은 허용 목록에 있는 것뿐이다(협력사 시험과 같은 구조).
  로그인 없이 쓰는 공개 주소(웹훅 · 고객 공유 링크 · healthz)도 빼지 않는다 — 그런 요청은 프리랜서 세션을
  싣지 않아 문지기가 상관하지 않고, 프리랜서 세션으로 열면 막히는 것이 맞다.
* 허용 목록의 (endpoint, 방법)마다 문지기가 통과시킨다(핸들러는 부르지 않고 문지기 함수만). 주문 번호는 내 주문
  (연결 줄)으로 준다 — 남의 주문 404 는 겹 2 시험(test_freelancer_order_scope.py)이 본다.
  같은 자리에서 막힌 endpoint 하나를 음성 대조군으로 본다.
* 대표 허용 화면은 실제 요청으로 200: 홈 · 실측 판 · 내 수수료 · 알림 목록 · 주문 모바일 상세.
* 내 정보 저장은 문지기를 지난다(비밀번호 바꾸기) — 이름은 핸들러가 그대로 둔다(T17).
* 대조군: 프리랜서가 아닌 영업 직원 · 관리자 · 꺼진 프리랜서는 막히지 않는다.
* 비용: 직원 · 영업팀이 아닌 계정과 정적 파일은 프리랜서 설정을 읽지 않는다.
"""
from __future__ import annotations

import itertools

import pytest
from flask import g

import foms.services.auth.freelancer_scope as scope
from db import db_session
from foms.services.auth.freelancer_order_rights import OWN_ORDER_ENDPOINTS
from foms.services.auth.freelancer_scope import (
    FREELANCER_ALLOWED_ENDPOINTS,
    FREELANCER_DENIED_MSG,
    FREELANCER_METHOD_LIMITS,
    FREELANCER_ORDER_NOT_FOUND_MSG,
    freelancer_gate,
)
from foms.services.sales_commission.settings import add_rate, load_settings, save_freelancer
from models import Order, OrderFreelancerLink, User
from tests.domains.test_auth_finance import _login, _make_user

_match_seq = itertools.count(1)
_RATE = {"effective_month": "2030-01", "lahom_bp": 400, "haud_bp": 600, "personal_bp": 800}
_HOME = "/erp/dashboard"
# 프리랜서가 못 여는 대표(설계서 "허용하지 않는 것"): 주문 복사 · 지도 · 옛 목록(사내 채팅은 CHAT-DEL-01 로 지움, 통합 검색은
# 11-08 점검으로 내 주문만 거른 채 엶).
# 이력 검색은 11-07 결정으로 내 주문만 거른 뒤 열었다(freelancer_screens/history.py).
_DENIED_SAMPLE = (
    ("POST", "/api/orders/copy"),
    ("GET", "/map_view"),
    ("GET", "/"),
)


# --------------------------------------------------------------------------
# 시드
# --------------------------------------------------------------------------
def _freelancer(*, active: bool = True) -> User:
    """직원 · 영업팀 계정을 만들고 프리랜서로 지정한다(맞출 이름 · 요율은 가짜 값)."""
    user = _make_user("STAFF", "SALES")
    version, _cfg, _changed = save_freelancer(
        db_session, user.id,
        {"match_name": f"가짜문지기{next(_match_seq)}", "start_month": "2020-01", "tax_type": "NONE",
         "active": active},
        base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    add_rate(db_session, user.id, _RATE, base_version=version, actor_user_id=None)
    db_session.commit()
    return user


def _order() -> int:
    sd = {
        "parties": {"manager": {"name": "아무개"}, "orderer": {"name": "라홈"}, "customer": {"name": "문지기고객"}},
        "schedule": {"measurement": {"date": "2030-01-05"}},
        "items": [{"product_name": "가짜장", "price": 1_000_000}],
        "workflow": {"stage": "MEASURE"},
    }
    order = Order(
        received_date="2030-01-01", customer_name="문지기고객", phone="010-0000-0000", address="가짜시",
        product="가짜장", status="MEASURE", manager_name="아무개", is_erp_order=True, structured_data=sd,
        erp_stage_code="MEASURE", erp_measurement_date="2030-01-05",
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _link(order_id: int, user: User) -> None:
    """주문을 이 프리랜서의 담당 주문으로 만든다(연결 줄 — 겹 2 가 보는 "내 주문")."""
    db_session.add(OrderFreelancerLink(order_id=order_id, user_id=user.id, relation="MANAGER_PRIMARY"))
    db_session.commit()


def _client(app, user: User):
    client = app.test_client()
    _login(client, user)
    return client


def _sample_path(rule, order_id: int) -> str:
    """규칙에 맞는 임의 URL. 정수 인자는 주문 id(프리랜서와 연결 없는 행)."""
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


def _is_gate_response(resp) -> bool:
    """문지기가 만든 응답인가 — 403 + 문지기 문구, 또는 프리랜서 홈으로 302."""
    if resp.status_code == 403:
        return (resp.get_json(silent=True) or {}).get("error") == FREELANCER_DENIED_MSG
    return resp.status_code == 302 and resp.headers.get("Location", "").endswith(_HOME)


def _gate_result(app, user: User, method: str, path: str):
    """핸들러 없이 문지기 함수만 부른 결과(None = 통과)."""
    with app.test_request_context(path, method=method):
        g.current_user = user
        return freelancer_gate()


# --------------------------------------------------------------------------
# 허용 목록 자체
# --------------------------------------------------------------------------
def test_allowlist_names_are_real_endpoints(app):
    """이름이 틀리거나 라우트 이름이 바뀌면 허용이 조용히 사라진다 — 모두 url_map 에 있어야 한다."""
    rules = {}
    for rule in app.url_map.iter_rules():
        rules.setdefault(rule.endpoint, set()).update(rule.methods)
    assert sorted(FREELANCER_ALLOWED_ENDPOINTS - set(rules)) == []
    for endpoint, methods in FREELANCER_METHOD_LIMITS.items():
        assert endpoint in FREELANCER_ALLOWED_ENDPOINTS, endpoint
        assert methods <= rules[endpoint], (endpoint, methods)
        assert rules[endpoint] - {"HEAD", "OPTIONS"} - methods, f"{endpoint}: 막는 방법이 없으면 제한이 필요 없다"


# --------------------------------------------------------------------------
# 문지기 래칫 — 모든 규칙
# --------------------------------------------------------------------------
def test_every_rule_outside_allowlist_is_blocked_for_freelancer(app):
    fl = _freelancer()
    order_id = _order()
    client = _client(app, fl)
    checked = 0
    leaks = []
    for rule in app.url_map.iter_rules():
        allowed_methods = None
        if rule.endpoint in FREELANCER_ALLOWED_ENDPOINTS:
            allowed_methods = FREELANCER_METHOD_LIMITS.get(rule.endpoint)
            if allowed_methods is None:
                continue
        path = _sample_path(rule, order_id)
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            if allowed_methods is not None and method in allowed_methods:
                continue
            resp = client.open(path, method=method)
            checked += 1
            if rule.endpoint in OWN_ORDER_ENDPOINTS:
                # 주문 일 API(D27) — 이 주문은 내 것이 아니라 다른 주문 API 와 같은 404 "주문을 찾을 수 없어요."(11-08).
                body = resp.get_json(silent=True) or {}
                json_like = "/api/" in path or method != "GET"
                if resp.status_code != 404 or (json_like and body.get("error") != FREELANCER_ORDER_NOT_FOUND_MSG):
                    leaks.append((rule.endpoint, method, path, resp.status_code))
            elif "/api/" in path or method != "GET":
                body = resp.get_json(silent=True) or {}
                if resp.status_code != 403 or body.get("error") != FREELANCER_DENIED_MSG:
                    leaks.append((rule.endpoint, method, path, resp.status_code))
            elif resp.status_code != 302 or not resp.headers.get("Location", "").endswith(_HOME):
                leaks.append((rule.endpoint, method, path, resp.status_code))
    assert checked > 400, checked
    assert leaks == [], leaks[:20]


def test_every_allowlisted_endpoint_passes_the_gate(app):
    """허용한 (endpoint, 방법)은 문지기를 지난다. 같은 자리의 막힌 endpoint 가 음성 대조군."""
    fl = _freelancer()
    order_id = _order()
    _link(order_id, fl)
    blocked = []
    checked = 0
    for rule in app.url_map.iter_rules():
        if rule.endpoint not in FREELANCER_ALLOWED_ENDPOINTS:
            continue
        limits = FREELANCER_METHOD_LIMITS.get(rule.endpoint)
        path = _sample_path(rule, order_id)
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            if limits is not None and method not in limits:
                continue
            checked += 1
            if _gate_result(app, fl, method, path) is not None:
                blocked.append((rule.endpoint, method, path))
    assert checked >= len(FREELANCER_ALLOWED_ENDPOINTS), checked
    assert blocked == []

    denied = _gate_result(app, fl, "POST", "/api/orders/copy")
    assert denied is not None and denied[1] == 403


# --------------------------------------------------------------------------
# 대표 허용 화면 — 실제 요청
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path", [
    _HOME,
    "/erp/measurement",
    "/erp/my-commission",
    "/erp/api/notifications",
    "/erp/api/notifications/badge",
])
def test_representative_allowed_screens_open_for_freelancer(app, path):
    client = _client(app, _freelancer())
    resp = client.get(path)
    assert resp.status_code == 200, (path, resp.status_code, resp.headers.get("Location"))


def test_order_mobile_detail_passes_gate_for_freelancer(app):
    """내 주문 화면은 문지기를 지난다(남의 주문 404 는 겹 2 시험이 본다)."""
    fl = _freelancer()
    client = _client(app, fl)
    order_id = _order()
    _link(order_id, fl)
    resp = client.get(f"/erp/orders/{order_id}/mobile")
    assert resp.status_code == 200, resp.status_code
    assert not _is_gate_response(client.get(f"/api/orders/{order_id}/structured"))


def test_freelancer_is_sent_home_from_denied_pages_and_can_logout(app):
    client = _client(app, _freelancer())
    for method, path in _DENIED_SAMPLE:
        assert _is_gate_response(client.open(path, method=method)), (method, path)
    out = client.post("/logout")
    assert out.status_code == 302
    with client.session_transaction() as sess:
        assert "user_id" not in sess


def test_profile_post_passes_gate_but_name_stays(app):
    """T17: 비밀번호를 바꾸려고 저장(POST)은 문지기를 지난다. 이름은 핸들러가 그대로 둔다
    (자세한 시험: tests/security/test_freelancer_edit_guards.py)."""
    fl = _freelancer()
    fl_id, before = fl.id, fl.name
    client = _client(app, fl)
    assert client.get("/profile").status_code == 200

    resp = client.post("/profile", data={"name": "직원이름흉내"})
    assert not _is_gate_response(resp), resp.status_code
    assert resp.status_code == 302
    db_session.expire_all()
    assert db_session.get(User, fl_id).name == before


# --------------------------------------------------------------------------
# 대조군 — 막히지 않는 계정
# --------------------------------------------------------------------------
@pytest.mark.parametrize("role,team", [("STAFF", "SALES"), ("STAFF", "MEASURE"), ("ADMIN", None), ("STAFF", "CS")])
def test_non_freelancers_are_not_gated(app, role, team):
    _freelancer()  # 설정 줄이 있어도 지정되지 않은 사람은 그대로다
    user = _make_user(role, team)
    for method, path in _DENIED_SAMPLE:
        assert _gate_result(app, user, method, path) is None, (role, team, method, path)
    resp = _client(app, user).get("/api/foms/search/fragment?q=x")
    assert not _is_gate_response(resp), resp.status_code


def test_inactive_freelancer_is_treated_as_normal_staff(app):
    """설계서 §6.3: 막는 것은 켜진 프리랜서뿐 — 꺼 두면 보통 영업 직원과 같다."""
    off = _freelancer(active=False)
    for method, path in _DENIED_SAMPLE:
        assert _gate_result(app, off, method, path) is None, (method, path)
    assert not _is_gate_response(_client(app, off).get("/api/foms/search/fragment?q=x"))


# --------------------------------------------------------------------------
# 비용 — 프리랜서가 될 수 없는 계정 · 정적 파일은 설정을 안 읽는다
# --------------------------------------------------------------------------
def test_gate_reads_settings_only_for_sales_staff(app, monkeypatch):
    calls = []
    real = scope.is_freelancer

    def counting(db, user):
        calls.append(user.id)
        return real(db, user)

    monkeypatch.setattr(scope, "is_freelancer", counting)
    for role, team in (("ADMIN", None), ("STAFF", "CS"), ("STAFF", "CONSTRUCTION"), ("MANAGER", "CS")):
        _client(app, _make_user(role, team)).get("/erp/api/notifications/badge")
    sales = _make_user("STAFF", "SALES")
    sales_client = _client(app, sales)
    sales_client.get("/static/css/foundation/erp-pro.css")
    assert calls == []

    # 양성 대조군: 영업 직원 · 영업 매니저(D27 — 매니저 등급도 프리랜서가 될 수 있다)의 일반 요청은 설정을 한 번 본다.
    sales_client.get("/erp/api/notifications/badge")
    manager = _make_user("MANAGER", "SALES")
    _client(app, manager).get("/erp/api/notifications/badge")
    assert calls == [sales.id, manager.id]


# --------------------------------------------------------------------------
# 주문 폼 라홈 제품 고르기 — 계산기 설정 목록 읽기(스테이징 QA 결함 1)
# --------------------------------------------------------------------------
# static/js/orders/erp-spec-calc.js 가 주문 편집 · 등록 화면에서 부르는 것 전부(GET).
_CATALOG_READS = {
    "/api/wdcalculator/products": ("wdcalculator.api_wdcalculator_get_products", "products"),
    "/api/wdcalculator/spec-field-presets": ("wdcalculator.api_wdcalculator_get_spec_field_presets",
                                             "spec_field_presets"),
    "/api/wdcalculator/additional-options/categories": ("wdcalculator.api_wdcalculator_get_categories", "categories"),
}
# 계산기에서 계속 막는 것 — 제품 설정 화면 · 설정 바꾸기 · 비고 묶음 읽기(설정 화면용). 계산기 화면 · 견적 ·
# 주문 찾기 · 잇기는 화면 묶음으로 열었다(freelancer_screens/wdcalculator.py — 내 견적 · 내 주문만, 11-07).
_WDC_STILL_DENIED = (
    ("POST", "/api/wdcalculator/products"),
    ("DELETE", "/api/wdcalculator/products/1"),
    ("POST", "/api/wdcalculator/spec-field-presets"),
    ("POST", "/api/wdcalculator/additional-options/categories"),
    ("POST", "/api/wdcalculator/notes/categories"),
    ("GET", "/api/wdcalculator/notes/categories"),
    ("GET", "/wdcalculator/product-settings"),
)


def test_order_form_catalog_reads_open_for_freelancer(app):
    """주문 폼 제품 고르기가 쓰는 계산기 설정 목록 3개는 열리고, 돌려주는 것은 설정 목록 한 칸뿐이다."""
    rules = {}
    for rule in app.url_map.iter_rules():
        if rule.rule in _CATALOG_READS:
            rules.setdefault(rule.rule, {})[rule.endpoint] = rule.methods - {"HEAD", "OPTIONS"}
    for path, (endpoint, _key) in _CATALOG_READS.items():
        assert endpoint in FREELANCER_ALLOWED_ENDPOINTS, endpoint
        assert rules[path][endpoint] == {"GET"}, (path, rules[path])  # GET 전용 라우트(쓰기는 다른 endpoint)
        assert endpoint not in FREELANCER_METHOD_LIMITS

    fl = _freelancer()
    order_id = _order()
    _link(order_id, fl)
    client = _client(app, fl)
    for path, (_endpoint, key) in _CATALOG_READS.items():
        resp = client.get(path)
        assert resp.status_code == 200, (path, resp.status_code)
        body = resp.get_json()
        assert body["success"] is True and set(body) == {"success", key}, (path, sorted(body))

    # 계산기 설정 바꾸기 · 설정 화면은 그대로 막힌다.
    for method, path in _WDC_STILL_DENIED:
        resp = client.open(path.format(oid=order_id), method=method, json={} if method == "POST" else None)
        assert _is_gate_response(resp), (method, path, resp.status_code)


def test_catalog_reads_unchanged_for_normal_sales(app):
    """대조군: 프리랜서 아닌 영업 직원은 전과 같이 열린다(문지기가 상관하지 않는다)."""
    _freelancer()
    client = _client(app, _make_user("STAFF", "SALES"))
    for path in _CATALOG_READS:
        assert client.get(path).status_code == 200, path
    assert not _is_gate_response(client.get("/api/wdcalculator/search-orders?q=x"))
