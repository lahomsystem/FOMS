"""FCOMM-01 D26: 프리랜서의 예전 담당 주문은 보통 영업 직원과 같게.

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.6 (사용자 결정 11-07 "내 담당 예전 주문만 다 풀기").

* 판정: 내 주문 + 주문을 만든 날 · 기준 날짜(실측일 → 접수일 → 생성일)가 모두 시작 달 1일 전. 경계 날짜, 남의 주문,
  꺼진 프리랜서, 시작 달 뒤에 만들고 실측일만 앞으로 적은 주문(막힘)을 본다.
* 문지기(전수): :data:`LEGACY_ORDER_ENDPOINTS` 의 모든 (규칙, 방법)을 예전 주문으로 부르면 통과, 새 주문 · 남의
  예전 주문으로 부르면 문지기 응답. 목록에 관리자 · 협력사 · 회계 전용 · 휴지통 영구 삭제 · 채팅이 끼지 않는다.
* 사람 단위 막기: 문지기가 "예전 주문만" 표시를 남긴 요청에서만 금융 정책 · 입금 확인 · PUSH 종류 · 퀘스트 단계가 풀린다.
* 실제 요청: 예전 주문의 발주사 바꾸기 200, 새 주문은 그대로 403. 예전 주문 퀘스트 읽기는 문지기를 지난다.
"""
from __future__ import annotations

import copy
import itertools
from typing import Optional

import pytest
from flask import g
from werkzeug.exceptions import NotFound

from db import db_session
from foms.services.auth.freelancer_edit_guards import (
    ORDERER_LOCKED_MSG,
    freelancer_push_kind_denial,
    freelancer_quest_stage_denial,
)
from foms.services.auth.freelancer_legacy import (
    LEGACY_ORDER_ENDPOINTS,
    freelancer_legacy_order,
    freelancer_request_is_legacy,
    mark_if_legacy,
)
from foms.services.auth.freelancer_scope import FREELANCER_DENIED_MSG, freelancer_gate, is_freelancer_request_allowed
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.orders.structured_put_guards import can_confirm_payment
from foms.services.sales_commission import calc
from foms.services.sales_commission.settings import add_rate, load_settings, save_freelancer
from models import Order, OrderFreelancerLink, User
from tests.domains.test_auth_finance import _login, _make_user

_seq = itertools.count(1)
_RATE = {"effective_month": "2030-01", "lahom_bp": 400, "haud_bp": 600, "personal_bp": 800}
#: 시험 프리랜서는 2030-01 에 시작한다 — 시험이 지금 만드는 주문은 모두 시작 달 전에 만든 것이다.
_START = "2030-01"
_OLD_DAY = "2029-12-31"   # 시작 달 하루 전 — 예전 주문
_NEW_DAY = "2030-01-01"   # 시작 달 1일 — 수수료 대상(새 주문)
_HOME = "/erp/dashboard"
#: 목록에 끼면 안 되는 이름 앞자리(관리자 · 협력사 · 회계 전용 · 휴지통 영구 삭제 · 채팅 · 판 화면).
_FORBIDDEN_PREFIXES = ("admin.", "partner", "erp_partner", "sales_commission", "order_trash.", "chat.",
                       "erp_drawing_workbench.", "erp_orders_drawing_wizard.")
_FORBIDDEN_ENDPOINTS = {"erp_orders_completion.api_settlement_deduction_void"}


# --------------------------------------------------------------------------
# 시드
# --------------------------------------------------------------------------
def _freelancer(*, start: str = _START, active: bool = True) -> User:
    user = _make_user("STAFF", "SALES")
    user.match_name = f"가짜예전담당{next(_seq)}"
    version, _cfg, _changed = save_freelancer(
        db_session, user.id,
        {"match_name": user.match_name, "start_month": start, "tax_type": "NONE", "active": active},
        base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    add_rate(db_session, user.id, _RATE, base_version=version, actor_user_id=None)
    db_session.commit()
    return user


def _order(manager: str, *, measured: Optional[str], received: Optional[str] = None) -> int:
    sd = {
        "parties": {"manager": {"name": manager}, "orderer": {"name": "라홈"},
                    "customer": {"name": "예전고객", "phone": "02-0000-0000"}},
        "site": {"address_full": "가짜시 가짜로 1"},
        "items": [{"product_name": "가짜장", "price": 1_000_000}],
        "workflow": {"stage": "MEASURE"},
    }
    if measured:
        sd["schedule"] = {"measurement": {"date": measured}}
    order = Order(
        received_date=received or "", customer_name="예전고객", phone="02-0000-0000", address="가짜시 가짜로 1",
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
    old = _order(fl.match_name, measured=_OLD_DAY)
    new = _order(fl.match_name, measured=_NEW_DAY)
    others_old = _order("남의담당", measured=_OLD_DAY)
    for oid in (old, new):
        _link(oid, fl)
    return {"fl": fl, "old": old, "new": new, "others_old": others_old}


# --------------------------------------------------------------------------
# 판정
# --------------------------------------------------------------------------
def test_boundary_and_basis_dates(app, world):
    fl = world["fl"]
    assert freelancer_legacy_order(db_session, fl, world["old"]) is True
    assert freelancer_legacy_order(db_session, fl, world["new"]) is False
    assert freelancer_legacy_order(db_session, fl, world["others_old"]) is False  # 내 주문 아님
    assert freelancer_legacy_order(db_session, fl, 99_999_999) is False
    by_received = _order(fl.match_name, measured=None, received="2029-12-01")
    late_received = _order(fl.match_name, measured=None, received="2030-01-02")
    for oid in (by_received, late_received):
        _link(oid, fl)
    assert freelancer_legacy_order(db_session, fl, by_received) is True    # 실측 없으면 접수일
    assert freelancer_legacy_order(db_session, fl, late_received) is False


def test_new_order_with_backdated_measurement_is_not_legacy(app):
    """시작 달 뒤에 만든 주문은 실측일을 앞 달로 적어도 예전 주문이 아니다(R1 회귀가 잡은 길)."""
    fl = _freelancer(start="2020-01")
    oid = _order(fl.match_name, measured="2019-12-01")
    _link(oid, fl)
    assert freelancer_legacy_order(db_session, fl, oid) is False


def test_inactive_freelancer_and_bad_inputs(app):
    fl = _freelancer(active=False)
    oid = _order(fl.match_name, measured=_OLD_DAY)
    _link(oid, fl)
    assert freelancer_legacy_order(db_session, fl, oid) is False
    assert calc.is_before_start(_OLD_DAY, None, None, "2030-1") is False      # 시작 달 형식 틀림 → 풀지 않음
    assert calc.is_before_start(None, None, None, _START) is False           # 기준 날짜 없음 → 풀지 않음
    assert calc.is_before_start(_OLD_DAY, None, None, _START) is True
    assert calc.is_eligible(_OLD_DAY, None, None, _START) is False           # 두 판정은 서로 반대쪽


# --------------------------------------------------------------------------
# 문지기 — 목록 전수
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
    for endpoint in sorted(LEGACY_ORDER_ENDPOINTS):
        for rule in rules[endpoint]:
            for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
                yield endpoint, rule, method


def _gate(app, user: User, method: str, path: str):
    """(문지기 결과, 예전 주문 표시). 화면 요청의 남의 주문은 문지기가 404 를 던진다 — 막힘으로 센다."""
    with app.test_request_context(path, method=method):
        g.current_user = user
        try:
            result = freelancer_gate()
        except NotFound:
            result = 404
        return result, freelancer_request_is_legacy()


def test_legacy_endpoints_are_real_order_scoped_and_not_privileged(app):
    rules = _rules(app)
    assert sorted(set(LEGACY_ORDER_ENDPOINTS) - set(rules)) == []
    for endpoint, names in LEGACY_ORDER_ENDPOINTS.items():
        assert names == ("order_id",)
        assert all("order_id" in rule.arguments for rule in rules[endpoint]), endpoint
        assert not endpoint.startswith(_FORBIDDEN_PREFIXES), endpoint
        assert endpoint not in _FORBIDDEN_ENDPOINTS


def test_gate_opens_every_legacy_endpoint_only_for_old_own_order(app, world):
    fl = world["fl"]
    checked = 0
    for endpoint, rule, method in _calls(app):
        opened, flagged = _gate(app, fl, method, _path(rule, world["old"]))
        assert opened is None and flagged, (endpoint, method)
        # 원래 허용 목록 문(옛 편집 화면 GET 등)은 새 내 주문에도 열린다 — 그때는 남의 주문만 막힘을 본다.
        already_open = is_freelancer_request_allowed(endpoint, method)
        for blocked in ((world["others_old"],) if already_open else (world["new"], world["others_old"])):
            denied, flagged = _gate(app, fl, method, _path(rule, blocked))
            assert denied is not None and not flagged, (endpoint, method, blocked)
        checked += 1
    assert checked >= len(LEGACY_ORDER_ENDPOINTS)


def test_non_freelancer_is_untouched(app, world):
    staff = _make_user("STAFF", "SALES")
    for endpoint, rule, method in _calls(app):
        assert _gate(app, staff, method, _path(rule, world["new"]))[0] is None, endpoint


# --------------------------------------------------------------------------
# 사람 단위 막기는 표시가 있을 때만 풀린다
# --------------------------------------------------------------------------
@pytest.mark.parametrize("which, unlocked", [("old", True), ("new", False), ("others_old", False)])
def test_person_level_locks_follow_request_mark(app, world, which, unlocked):
    fl = world["fl"]
    finance = POLICY_REGISTRY["FINANCE_MUTATION"]
    with app.test_request_context("/"):
        g.current_user = fl
        assert evaluate_policy(finance, fl).allowed is False  # 표시 전에는 늘 막힘
        assert mark_if_legacy(db_session, fl, [world[which]]) is unlocked
        assert freelancer_request_is_legacy() is unlocked
        assert evaluate_policy(finance, fl).allowed is unlocked
        assert can_confirm_payment(fl) is unlocked
        assert (freelancer_quest_stage_denial("DRAWING") is None) is unlocked
        assert (freelancer_push_kind_denial({"push_kind": "drawing"}) is None) is unlocked


def test_mixed_ids_do_not_mark(app, world):
    fl = world["fl"]
    with app.test_request_context("/"):
        g.current_user = fl
        assert mark_if_legacy(db_session, fl, [world["old"], world["new"]]) is False
        assert mark_if_legacy(db_session, fl, []) is False
        assert freelancer_request_is_legacy() is False


# --------------------------------------------------------------------------
# 실제 요청
# --------------------------------------------------------------------------
def _put_orderer(client, order_id: int, orderer: str):
    db_session.expire_all()
    sd = copy.deepcopy(db_session.get(Order, order_id).structured_data)
    sd["parties"]["orderer"]["name"] = orderer
    return client.put(f"/api/orders/{order_id}/structured", json={"structured_data": sd})


def _orderer_of(order_id: int) -> str:
    db_session.expire_all()
    return db_session.get(Order, order_id).structured_data["parties"]["orderer"]["name"]


def test_orderer_change_opens_only_on_old_order(app, world):
    client = _client(app, world["fl"])
    assert _put_orderer(client, world["old"], "하우드").status_code == 200
    assert _orderer_of(world["old"]) == "하우드"
    resp = _put_orderer(client, world["new"], "하우드")
    assert resp.status_code == 403 and resp.get_json()["error"] == ORDERER_LOCKED_MSG
    assert _orderer_of(world["new"]) == "라홈"


def test_closed_api_passes_gate_on_old_order_only(app, world):
    client = _client(app, world["fl"])
    old = client.get(f"/api/orders/{world['old']}/quest")
    assert (old.get_json(silent=True) or {}).get("error") != FREELANCER_DENIED_MSG and old.status_code != 302
    new = client.get(f"/api/orders/{world['new']}/quest")
    assert new.status_code == 403 and new.get_json()["error"] == FREELANCER_DENIED_MSG
    others = client.get(f"/api/orders/{world['others_old']}/quest")
    assert others.status_code == 403 and others.get_json()["error"] == FREELANCER_DENIED_MSG
