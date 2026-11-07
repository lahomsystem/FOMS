"""FCOMM-01 J8 · D27: 프리랜서 이름 고정과, 자기 주문 발주사 바꾸기가 회사 직원과 같은지 (플랜 T17 B · 11-07 D27).

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §1.2 J8 · §6.3 겹 4 · §6.5, 검토 원장 A1 · A13.

* 발주사: D27(11-07)부터 켜진 프리랜서도 자기 주문의 발주사를 회사 직원처럼 바꾼다(예전 403 은 걷음).
* 내 정보: 프리랜서도 비밀번호는 바꾼다. 이름은 언제나 그대로이고 안내 한 줄이 뜬다. 대조군: 보통 직원은 이름을 바꾼다.
"""
from __future__ import annotations

import copy
import itertools

import pytest
from werkzeug.security import check_password_hash

from db import db_session
from foms.services.auth.freelancer_edit_guards import PROFILE_NAME_LOCKED_MSG
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
def test_freelancer_changes_orderer_of_own_registered_order_like_staff(fl_world):
    """D27: 자기 주문이면 등록된 주문의 발주사도 회사 영업 직원처럼 바꾼다(예전 D21/A13 막기는 걷음)."""
    resp = _put_orderer(fl_world["client"], fl_world["registered"], "하우드")
    assert resp.status_code == 200
    assert _orderer_of(fl_world["registered"]) == "하우드"


def test_freelancer_still_cannot_touch_other_order(app, fl_world):
    other = _order("남의담당")
    resp = _put_orderer(fl_world["client"], other, "하우드")
    assert resp.status_code == 404
    assert _orderer_of(other) == "라홈"


# --------------------------------------------------------------------------
# 내 정보 — 이름 고정(J8)
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
