"""FCOMM-01 3단계 겹 4 · J8: 프리랜서가 스스로 수수료 주인 · 이름을 바꾸는 길 (플랜 T17 B).

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §1.2 J8 · §6.3 겹 4 · §6.5, 검토 원장 A1 · A13.

* 발주사: 켜진 프리랜서가 **등록된** 주문의 발주사를 바꾸는 structured PUT 은 403(라홈→하우드, 내 맞출 이름으로/에서).
  초안 저장 · 첫 등록(초안 → 주문)은 된다. 이름 정리(앞뒤 공백)만 다른 것 · 발주사를 안 싣는 저장은 바꾼 것이 아니다.
  대조군: 프리랜서 아닌 영업 직원 · 꺼진 프리랜서는 그대로 바꾼다.
* 내 정보: 프리랜서도 비밀번호는 바꾼다. 이름은 언제나 그대로이고 안내 한 줄이 뜬다. 대조군: 보통 직원은 이름을 바꾼다.
"""
from __future__ import annotations

import copy
import itertools

import pytest
from werkzeug.security import check_password_hash

from db import db_session
from foms.services.auth.freelancer_edit_guards import (
    ORDERER_LOCKED_MSG,
    PROFILE_NAME_LOCKED_MSG,
    _UNCHANGED,
    _incoming_orderer_name,
)
from foms.services.sales_commission.settings import add_rate, load_settings, save_freelancer
from models import Order, OrderFreelancerLink, User
from tests.domains.test_auth_finance import _login, _make_user

_seq = itertools.count(1)
_RATE = {"effective_month": "2030-01", "lahom_bp": 400, "haud_bp": 600, "personal_bp": 800}
_NEW_PASSWORD = "fcomm2030pass"


# --------------------------------------------------------------------------
# 시드(가짜 값)
# --------------------------------------------------------------------------
def _freelancer(*, active: bool = True) -> User:
    user = _make_user("STAFF", "SALES")
    user.match_name = f"가짜수정담당{next(_seq)}"
    version, _cfg, _changed = save_freelancer(
        db_session, user.id,
        {"match_name": user.match_name, "start_month": "2020-01", "tax_type": "NONE", "active": active},
        base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    add_rate(db_session, user.id, _RATE, base_version=version, actor_user_id=None)
    db_session.commit()
    return user


def _order(manager: str, *, orderer: str = "라홈", draft: bool = False) -> int:
    sd = {
        "parties": {
            "manager": {"name": manager},
            "orderer": {"name": orderer},
            "customer": {"name": "수정고객", "phone": "010-0000-0000"},
        },
        "site": {"address_full": "가짜시 가짜로 1"},
        "schedule": {"measurement": {"date": "2030-01-05"}},
        "items": [{"product_name": "가짜장", "price": 1_000_000}],
        "workflow": {"stage": "MEASURE"},
    }
    if draft:
        sd["meta"] = {"draft": True}
    order = Order(
        received_date="2030-01-01", customer_name="수정고객", phone="010-0000-0000", address="가짜시 가짜로 1",
        product="가짜장", status="DRAFT" if draft else "MEASURE", manager_name=manager, is_erp_order=True,
        structured_data=sd, erp_stage_code="MEASURE", erp_measurement_date="2030-01-05",
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _ensure_link(order_id: int, user: User) -> None:
    """프리랜서가 문지기 겹 2 를 지나도록 내 주문으로 묶는다(훅이 이미 묶었으면 그대로)."""
    if not db_session.query(OrderFreelancerLink).filter_by(order_id=order_id, user_id=user.id).first():
        db_session.add(OrderFreelancerLink(order_id=order_id, user_id=user.id, relation="CREATOR"))
        db_session.commit()


def _client(app, user: User):
    client = app.test_client()
    _login(client, user)
    return client


def _put_orderer(client, order_id: int, orderer: str):
    db_session.expire_all()
    sd = copy.deepcopy(db_session.get(Order, order_id).structured_data)
    sd["parties"]["orderer"]["name"] = orderer
    return client.put(f"/api/orders/{order_id}/structured", json={"structured_data": sd})


def _orderer_of(order_id: int) -> str:
    db_session.expire_all()
    return db_session.get(Order, order_id).structured_data["parties"]["orderer"]["name"]


@pytest.fixture
def fl_world(app):
    fl = _freelancer()
    registered = _order(fl.match_name)
    draft = _order(fl.match_name, draft=True)
    for oid in (registered, draft):
        _ensure_link(oid, fl)
    return {"fl": fl, "registered": registered, "draft": draft, "client": _client(app, fl)}


# --------------------------------------------------------------------------
# 발주사 — 등록된 주문
# --------------------------------------------------------------------------
@pytest.mark.parametrize("new_orderer", ["하우드", "MATCH", ""])
def test_freelancer_cannot_change_orderer_of_registered_order(fl_world, new_orderer):
    """라홈 → 하우드 · 내 맞출 이름(개인영업) · 지우기 모두 거부, 저장된 값은 그대로."""
    target = fl_world["fl"].match_name if new_orderer == "MATCH" else new_orderer
    resp = _put_orderer(fl_world["client"], fl_world["registered"], target)
    assert resp.status_code == 403
    assert resp.get_json() == {"success": False, "data": None, "error": ORDERER_LOCKED_MSG}
    assert _orderer_of(fl_world["registered"]) == "라홈"


def test_freelancer_cannot_move_orderer_away_from_own_name(app):
    """개인영업(맞출 이름) → 라홈 도 거부 — 프리랜서 이름에서 빼는 것도 수수료를 바꾼다."""
    fl = _freelancer()
    oid = _order(fl.match_name, orderer=fl.match_name)
    _ensure_link(oid, fl)
    resp = _put_orderer(_client(app, fl), oid, "라홈")
    assert resp.status_code == 403
    assert _orderer_of(oid) == fl.match_name


def test_same_orderer_or_no_orderer_in_payload_is_not_a_change(fl_world):
    client, oid = fl_world["client"], fl_world["registered"]
    # 앞뒤 공백만 다르면 수수료 판정과 같은 정리로 같은 이름 — 저장된다
    assert _put_orderer(client, oid, "  라홈 ").status_code == 200
    # 발주사를 싣지 않는 저장(메모만) — 막지 않는다
    resp = client.put(f"/api/orders/{oid}/structured", json={"notes": "프리랜서 메모"})
    assert resp.status_code == 200
    db_session.expire_all()
    assert db_session.get(Order, oid).notes == "프리랜서 메모"


# --------------------------------------------------------------------------
# 발주사 — 초안 · 첫 등록은 된다
# --------------------------------------------------------------------------
def test_freelancer_picks_orderer_at_first_registration(fl_world):
    """초안을 등록하는 저장에서 개인영업(맞출 이름)을 고른다 — 등록 뒤에는 잠긴다."""
    fl, oid, client = fl_world["fl"], fl_world["draft"], fl_world["client"]
    resp = _put_orderer(client, oid, fl.match_name)
    assert resp.status_code == 200, resp.get_json()
    db_session.expire_all()
    saved = db_session.get(Order, oid)
    assert saved.structured_data["parties"]["orderer"]["name"] == fl.match_name
    assert saved.structured_data["meta"]["draft"] is False  # 이 저장이 등록이었다
    # 이제 등록된 주문 — 다시 바꾸면 거부
    assert _put_orderer(client, oid, "하우드").status_code == 403
    assert _orderer_of(oid) == fl.match_name


# --------------------------------------------------------------------------
# 대조군 — 프리랜서 아닌 계정
# --------------------------------------------------------------------------
@pytest.mark.parametrize("who", ["sales", "inactive"])
def test_non_freelancers_still_change_orderer(app, who):
    if who == "sales":
        _freelancer()  # 설정 줄이 있어도 지정되지 않은 사람은 그대로
        user = _make_user("STAFF", "SALES")
    else:
        user = _freelancer(active=False)
    oid = _order("남의담당")
    resp = _put_orderer(_client(app, user), oid, "하우드")
    assert resp.status_code == 200, resp.get_json()
    assert _orderer_of(oid) == "하우드"


@pytest.mark.parametrize("structured_data,expected", [
    (None, _UNCHANGED),
    ({}, _UNCHANGED),
    ({"parties": None}, _UNCHANGED),
    ({"parties": {"customer": {"name": "x"}}}, _UNCHANGED),
    ({"parties": {"orderer": {"phone": "010"}}}, _UNCHANGED),
    ({"parties": {"orderer": {"name": "하우드"}}}, "하우드"),
    ({"parties": {"orderer": None}}, ""),
    ({"parties": ["x"]}, ""),
])
def test_incoming_orderer_follows_put_merge_rules(structured_data, expected):
    """PUT 의 parties 깊은 합치기와 같은 규칙 — 안 실은 칸은 옛 값이 남고, 사전이 아니면 통째로 바뀐다."""
    assert _incoming_orderer_name(structured_data) == expected


# --------------------------------------------------------------------------
# 내 정보 — 이름은 그대로, 비밀번호는 바뀐다
# --------------------------------------------------------------------------
def _profile_post(client, **form):
    return client.post("/profile", data=form, follow_redirects=True)


def test_freelancer_changes_password_but_not_name(app):
    fl = _freelancer()
    fl_id, before = fl.id, fl.name
    client = _client(app, fl)
    resp = _profile_post(client, name="직원이름흉내", current_password="pw", new_password=_NEW_PASSWORD,
                         confirm_password=_NEW_PASSWORD)
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert PROFILE_NAME_LOCKED_MSG in html
    assert "비밀번호가 성공적으로 변경되었습니다." in html
    db_session.expire_all()
    saved = db_session.get(User, fl_id)
    assert saved.name == before
    assert check_password_hash(saved.password, _NEW_PASSWORD)


def test_freelancer_profile_shows_name_readonly_and_same_name_has_no_notice(app):
    fl = _freelancer()
    fl_id, name = fl.id, fl.name
    client = _client(app, fl)
    page = client.get("/profile").get_data(as_text=True)
    assert 'id="name" name="name"' in page and 'autocomplete="name" readonly>' in page
    resp = _profile_post(client, name=name)
    assert PROFILE_NAME_LOCKED_MSG not in resp.get_data(as_text=True)
    # 이름 칸을 비워 보내도(읽기 전용 칸을 지운 요청) 이름은 그대로 — "이름을 입력해주세요" 로 막히지도 않는다
    resp = _profile_post(client, name="")
    assert "이름을 입력해주세요." not in resp.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.get(User, fl_id).name == name


@pytest.mark.parametrize("role,team", [("STAFF", "SALES"), ("STAFF", "CS")])
def test_non_freelancer_can_change_name(app, role, team):
    _freelancer()
    user = _make_user(role, team)
    user_id = user.id
    client = _client(app, user)
    assert 'autocomplete="name" readonly>' not in client.get("/profile").get_data(as_text=True)
    resp = _profile_post(client, name="바뀐직원이름")
    assert PROFILE_NAME_LOCKED_MSG not in resp.get_data(as_text=True)
    db_session.expire_all()
    assert db_session.get(User, user_id).name == "바뀐직원이름"
