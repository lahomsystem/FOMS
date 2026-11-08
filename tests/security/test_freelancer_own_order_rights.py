"""FCOMM-01 D27: 프리랜서도 자기 주문에서는 회사 영업 직원(매니저 등급 포함)과 같다 — 남의 주문만 안 된다.

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.6 (사용자 결정 11-07 "주문건만 자기 것만 보이고
이전 회사 소속일 때랑 동일한 사용").

* 문지기(전수): :data:`OWN_ORDER_ENDPOINTS` 의 모든 (규칙, 방법)을 내 주문으로 부르면 통과, 남의 주문 · 없는 주문은
  문지기 응답. 실측일이 언제든 같다(예전 D26 의 날짜 조건은 없다). 목록에 관리자 · 협력사 · 회계 전용 · 채팅이 없다.
* 매니저 등급 프리랜서: 문지기 · 주문 범위가 똑같이 걸리고, 자기 주문 일은 연다.
* 실제 요청: 내 주문 발주사 바꾸기 200, 금융 정책 = 보통 영업 직원과 같은 답.
* 검토 2(D27 반증): AS 기준 일정 잇기 · 영업 전달 배정은 읽을 수 없는 주문을 "없는 주문"과 같은 404 로 — 날짜 · 담당자가
  새지 않는다. 보통 직원은 그대로.
"""
from __future__ import annotations

import copy
import itertools

import pytest
from flask import g
from werkzeug.exceptions import NotFound

from db import db_session
from foms.services.auth.freelancer_order_rights import OWN_ORDER_ENDPOINTS
from foms.services.auth.freelancer_scope import (
    FREELANCER_DENIED_MSG,
    FREELANCER_ORDER_NOT_FOUND_MSG,
    could_be_freelancer,
    freelancer_gate,
    is_freelancer_request_allowed,
)
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.sales_commission.settings import add_rate, load_settings, save_freelancer
from models import Order, OrderFreelancerLink, User
from tests.domains.test_auth_finance import _login, _make_user

_seq = itertools.count(1)
_RATE = {"effective_month": "2030-01", "lahom_bp": 400, "haud_bp": 600, "personal_bp": 800}
_FORBIDDEN_PREFIXES = ("admin.", "partner", "erp_partner", "sales_commission", "chat.",
                       "erp_drawing_workbench.", "erp_orders_drawing_wizard.")
_FORBIDDEN_ENDPOINTS = {"erp_orders_completion.api_settlement_deduction_void"}


# --------------------------------------------------------------------------
# 시드
# --------------------------------------------------------------------------
def _freelancer(*, role: str = "STAFF") -> User:
    user = _make_user(role, "SALES")
    user.match_name = f"가짜권한담당{next(_seq)}"
    version, _cfg, _changed = save_freelancer(
        db_session, user.id,
        {"match_name": user.match_name, "start_month": "2020-01", "tax_type": "NONE", "active": True},
        base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    add_rate(db_session, user.id, _RATE, base_version=version, actor_user_id=None)
    db_session.commit()
    return user


def _order(manager: str, *, measured: str = "2030-01-05", built: str | None = None) -> int:
    sd = {
        "parties": {"manager": {"name": manager}, "orderer": {"name": "라홈"},
                    "customer": {"name": "권한고객", "phone": "02-0000-0000"}},
        "site": {"address_full": "가짜시 가짜로 1"},
        "schedule": {"measurement": {"date": measured}},
        "items": [{"product_name": "가짜장", "price": 1_000_000}],
        "workflow": {"stage": "MEASURE"},
    }
    if built:
        sd["schedule"]["construction"] = {"date": built}
    order = Order(
        received_date="2030-01-01", customer_name="권한고객", phone="02-0000-0000", address="가짜시 가짜로 1",
        product="가짜장", status="MEASURE", manager_name=manager, is_erp_order=True, structured_data=sd,
        erp_stage_code="MEASURE", erp_measurement_date=measured,
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _link(order_id: int, user: User) -> None:
    if not db_session.query(OrderFreelancerLink).filter_by(order_id=order_id, user_id=user.id).first():
        db_session.add(OrderFreelancerLink(order_id=order_id, user_id=user.id, relation="MANAGER_PRIMARY"))
        db_session.commit()


def _client(app, user: User):
    client = app.test_client()
    _login(client, user)
    return client


@pytest.fixture
def world(app):
    fl = _freelancer()
    old = _order(fl.match_name, measured="2019-12-01")   # 시작 달 전 실측 — 예전 D26 이 따로 보던 주문
    new = _order(fl.match_name)
    other = _order("남의담당", built="2030-02-01")
    for oid in (old, new):
        _link(oid, fl)
    return {"fl": fl, "old": old, "new": new, "other": other}


# --------------------------------------------------------------------------
# 목록 · 문지기 전수
# --------------------------------------------------------------------------
def _rules(app) -> dict:
    rules: dict = {}
    for rule in app.url_map.iter_rules():
        rules.setdefault(rule.endpoint, []).append(rule)
    return rules


def _path(rule, order_id: int) -> str:
    values = {}
    for arg, conv in rule._converters.items():
        kind = type(conv).__name__
        values[arg] = order_id if arg == "order_id" else (1 if kind == "IntegerConverter" else "x")
    return rule.build(values, append_unknown=False)[1]


def _calls(app):
    rules = _rules(app)
    for endpoint in sorted(OWN_ORDER_ENDPOINTS):
        for rule in rules[endpoint]:
            for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
                yield endpoint, rule, method


def _gate(app, user: User, method: str, path: str):
    """문지기 결과(None = 통과). 화면 요청의 남의 주문은 문지기가 404 를 던진다 — 막힘으로 센다."""
    with app.test_request_context(path, method=method):
        g.current_user = user
        try:
            return freelancer_gate()
        except NotFound:
            return 404


def test_own_order_endpoints_are_real_order_scoped_and_not_privileged(app):
    rules = _rules(app)
    assert sorted(set(OWN_ORDER_ENDPOINTS) - set(rules)) == []
    for endpoint, names in OWN_ORDER_ENDPOINTS.items():
        assert names == ("order_id",)
        assert all("order_id" in rule.arguments for rule in rules[endpoint]), endpoint
        assert not endpoint.startswith(_FORBIDDEN_PREFIXES), endpoint
        assert endpoint not in _FORBIDDEN_ENDPOINTS


@pytest.mark.parametrize("role", ["STAFF", "MANAGER"])
def test_gate_opens_every_order_endpoint_for_own_orders_only(app, world, role):
    fl = world["fl"] if role == "STAFF" else _freelancer(role="MANAGER")
    if role == "MANAGER":
        for oid in (world["old"], world["new"]):
            _link(oid, fl)
    checked = 0
    for endpoint, rule, method in _calls(app):
        for own in (world["old"], world["new"]):  # 실측일과 무관
            assert _gate(app, fl, method, _path(rule, own)) is None, (endpoint, method, own)
        assert _gate(app, fl, method, _path(rule, world["other"])) is not None, (endpoint, method)
        assert _gate(app, fl, method, _path(rule, 99_999_999)) is not None, (endpoint, method)
        checked += 1
    assert checked >= len(OWN_ORDER_ENDPOINTS)


def test_manager_freelancer_is_gated_like_staff_freelancer(app):
    manager = _make_user("MANAGER", "SALES")
    assert could_be_freelancer(manager) is True
    assert could_be_freelancer(_make_user("MANAGER", "CS")) is False
    # 프리랜서로 정하지 않은 영업 매니저는 문지기와 무관하다.
    assert _gate(app, manager, "GET", "/erp/history/") is None


def test_non_freelancer_is_untouched(app, world):
    staff = _make_user("STAFF", "SALES")
    for endpoint, rule, method in _calls(app):
        assert _gate(app, staff, method, _path(rule, world["other"])) is None, endpoint


# --------------------------------------------------------------------------
# 실제 요청 — 회사 직원과 같은 답
# --------------------------------------------------------------------------
def _put_orderer(client, order_id: int, orderer: str):
    db_session.expire_all()
    sd = copy.deepcopy(db_session.get(Order, order_id).structured_data)
    sd["parties"]["orderer"]["name"] = orderer
    return client.put(f"/api/orders/{order_id}/structured", json={"structured_data": sd})


def test_orderer_change_and_finance_same_as_staff(app, world):
    fl = world["fl"]
    fl_id = fl.id
    client = _client(app, fl)
    assert _put_orderer(client, world["new"], "하우드").status_code == 200
    db_session.expire_all()
    assert db_session.get(Order, world["new"]).structured_data["parties"]["orderer"]["name"] == "하우드"
    fl = db_session.get(User, fl_id)
    seller = _make_user("STAFF", "SALES")
    with app.test_request_context("/"):
        g.current_user = fl
        for policy_id in ("FINANCE_MUTATION", "ERP_EDIT", "STAFF_MUTATION"):
            assert evaluate_policy(POLICY_REGISTRY[policy_id], fl).allowed is \
                evaluate_policy(POLICY_REGISTRY[policy_id], seller).allowed, policy_id


def test_closed_api_opens_for_own_order(app, world):
    client = _client(app, world["fl"])
    for own in (world["old"], world["new"]):
        resp = client.get(f"/api/orders/{own}/quest")
        assert (resp.get_json(silent=True) or {}).get("error") != FREELANCER_DENIED_MSG and resp.status_code != 302
    other = client.get(f"/api/orders/{world['other']}/quest")
    missing = client.get("/api/orders/99999999/quest")
    # 남의 주문 = 없는 주문 = 다른 주문 API 와 같은 404 문구(11-08 점검 — 예전에는 403 "열 수 없는 화면").
    assert other.status_code == missing.status_code == 404
    assert other.get_json() == missing.get_json()
    assert other.get_json()["error"] == FREELANCER_ORDER_NOT_FOUND_MSG
    assert not is_freelancer_request_allowed("quest.api_order_quest_get", "GET")  # 허용 목록이 아니라 내 주문 규칙으로 열림


# --------------------------------------------------------------------------
# 검토 2 — AS 기준 주문은 읽을 수 있는 주문만
# --------------------------------------------------------------------------
@pytest.mark.parametrize("path,body_key,message", [
    ("/api/orders/{oid}/as/schedule-link", "ref_order_id", "기준 주문을 찾을 수 없습니다."),
    ("/api/orders/{oid}/sales-delivery", "ref_order_id", "기준 실측 주문을 찾을 수 없습니다."),
])
def test_as_reference_to_unreadable_order_is_not_found(app, world, path, body_key, message):
    client = _client(app, world["fl"])
    action = "link" if "schedule" in path else "assign"
    resp = client.post(path.format(oid=world["new"]), json={"action": action, body_key: world["other"]})
    body = resp.get_json() or {}
    assert resp.status_code == 404 and body.get("message") == message, body
    assert "2030-02-01" not in resp.get_data(as_text=True) and "남의담당" not in resp.get_data(as_text=True)
    missing = client.post(path.format(oid=world["new"]), json={"action": action, body_key: 99_999_999})
    assert missing.status_code == 404 and (missing.get_json() or {}).get("message") == message  # 같은 답


def test_as_reference_for_staff_unchanged(app, world):
    client = _client(app, _make_user("STAFF", "SALES"))
    resp = client.post(f"/api/orders/{world['new']}/as/schedule-link",
                       json={"action": "link", "ref_order_id": world["other"]})
    assert resp.status_code != 404 or (resp.get_json() or {}).get("message") != "기준 주문을 찾을 수 없습니다."
