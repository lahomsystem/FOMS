"""FCOMM-01 T18 반증 재검수 회귀 — 구멍 R1 · R2 · R4 · R6 · R7 · R9 가 닫혔는지, R3 은 추적 칸이 있는지.

원장: docs/plans/2026-11-06-freelancer-commission-review-ledger.md ④(재현 시험 3개가 통과해 구멍이 실재했다).
구멍마다 공격이 막혔는지와 함께 정상 길(음성 대조군)이 그대로인지 본다 — 전용 차감 API · 결제 확인 API ·
내 초안 토큰 · 내 중복 등록 · 내 생성 이벤트. 고객 · 이름 · 금액은 모두 가짜 값이다.
"""
from __future__ import annotations

import copy
import datetime
import itertools
from pathlib import Path
from types import SimpleNamespace

import pytest

from db import db_session
from foms.services.sales_commission.calc import sales_deduction_total
from foms.services.sales_commission.links import REL_CREATOR, creator_links, load_link_snapshot
from foms.services.sales_commission.read_model import SELF_EDIT_PATHS
from foms.services.sales_commission.settings import add_rate, load_settings, save_freelancer
from models import Order, OrderDraft, OrderEvent, OrderFreelancerLink, User
from tests.domains.test_auth_finance import _login, _make_user

_ROOT = Path(__file__).resolve().parents[2]
_seq = itertools.count(1)
_RATE = {"effective_month": "2030-01", "lahom_bp": 400, "haud_bp": 600, "personal_bp": 800}
_BANNER_TITLE = "foms-as-drift-banner__title"  # 배너가 실제로 그려질 때만 나오는 표식(CSS 링크 이름과 다르다)
_CONFIRM_FORGERY = {"deposit_confirmed": True, "deposit_confirmed_by": "가짜회계팀장",
                    "deposit_confirmed_by_user_id": 1, "deposit_confirmed_at": "2030-01-01T00:00:00"}


# --------------------------------------------------------------------------
# 시드(가짜 값)
# --------------------------------------------------------------------------
def _person(user: User, match_name: str = "") -> SimpleNamespace:
    """요청이 끝나면 세션이 비워져 User 행이 떨어진다 — 시험이 쓰는 값만 미리 떠 둔다."""
    return SimpleNamespace(id=user.id, username=user.username, role=user.role, name=user.name,
                           match_name=match_name)


def _staff(team: str = "SALES") -> SimpleNamespace:
    return _person(_make_user("STAFF", team))


def _freelancer() -> SimpleNamespace:
    user = _staff()
    match_name = f"가짜재검담당{next(_seq)}"
    version, _cfg, _changed = save_freelancer(
        db_session, user.id,
        {"match_name": match_name, "start_month": "2020-01", "tax_type": "NONE", "active": True},
        base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    add_rate(db_session, user.id, _RATE, base_version=version, actor_user_id=None)
    db_session.commit()
    return _person(user, match_name)


def _sd(manager: str, customer: str, *, stage: str, cdate: str | None) -> dict:
    return {
        "parties": {"manager": {"name": manager}, "orderer": {"name": "라홈"},
                    "customer": {"name": customer, "phone": "010-9999-0000"}},
        "site": {"address_full": "가짜시 비밀동 1"},
        "schedule": {"measurement": {"date": "2030-01-05"}, "construction": {"date": cdate or ""}},
        "items": [{"product_name": "가짜장", "price": 1_000_000}],
        "workflow": {"stage": stage},
    }


def _order(manager: str = "남의담당", *, customer: str = "남의고객", extra: dict | None = None,
           stage: str = "MEASURE", cdate: str | None = None) -> int:
    sd = _sd(manager, customer, stage=stage, cdate=cdate)
    sd.update(copy.deepcopy(extra or {}))
    order = Order(
        received_date="2030-01-01", customer_name=customer, phone="010-9999-0000", address="가짜시 비밀동 1",
        product="가짜장", status=stage, manager_name=manager, is_erp_order=True, structured_data=sd,
        erp_stage_code=stage, erp_measurement_date="2030-01-05", erp_construction_date=cdate,
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _link(order_id: int, user: SimpleNamespace, relation: str = "MANAGER_PRIMARY") -> None:
    if db_session.query(OrderFreelancerLink).filter_by(order_id=order_id, user_id=user.id).first() is None:
        db_session.add(OrderFreelancerLink(order_id=order_id, user_id=user.id, relation=relation))
        db_session.commit()


def _client(app, user: SimpleNamespace):
    client = app.test_client()
    _login(client, user)
    return client


def _put_sd(client, order_id: int, sd: dict):
    return client.put(f"/api/orders/{order_id}/structured", json={"structured_data": sd},
                      headers={"Origin": "http://localhost"})


def _own_sd(order_id: int) -> dict:
    db_session.expire_all()
    return copy.deepcopy(db_session.get(Order, order_id).structured_data)


def _html(client, path: str) -> str:
    resp = client.get(path)
    assert resp.status_code == 200, path
    return resp.get_data(as_text=True)


def _with_link(sd: dict, ref_id: int) -> dict:
    sd["schedule"]["as_visit"] = {"date": "2030-01-09",
                                  "schedule_link": {"ref_order_id": ref_id, "ref_date": "2030-01-01"}}
    return sd


# --------------------------------------------------------------------------
# R1: AS 기준 일정 링크로 남의 주문 고객명 · 시공일 · 존재 여부 엿보기
# --------------------------------------------------------------------------
def test_put_schedule_link_to_unreadable_order_keeps_old_value(app):
    fl = _freelancer()
    own = _order(fl.match_name, customer="내고객")
    _link(own, fl)
    victim = _order(customer="피해자홍길동", cdate="2030-03-17", stage="CONSTRUCTION")
    client = _client(app, fl)
    assert client.get(f"/edit/{victim}").status_code == 404

    assert _put_sd(client, own, _with_link(_own_sd(own), victim)).status_code == 200
    as_visit = _own_sd(own)["schedule"]["as_visit"]
    assert "schedule_link" not in as_visit and as_visit["date"] == "2030-01-09"  # 링크만 버리고 저장은 된다
    html = _html(client, f"/edit/{own}")
    assert "피해자홍길동" not in html and "3/17" not in html

    # 없는 번호도 남의 주문과 같은 답 — "찾을 수 없습니다" 로 존재 여부를 알려 주지 않는다
    assert _put_sd(client, own, _with_link(_own_sd(own), 999999)).status_code == 200
    assert "schedule_link" not in _own_sd(own)["schedule"]["as_visit"]
    html = _html(client, f"/edit/{own}")
    assert _BANNER_TITLE not in html and "주문을 찾을 수 없습니다 (연결 끊김)" not in html


def test_banner_hides_existing_link_to_unreadable_order(app):
    """직원이 예전에 걸어 둔 링크(남의 주문)는 남기되, 프리랜서 화면에는 링크가 없는 것처럼 그린다."""
    fl = _freelancer()
    victim = _order(customer="피해자김비밀", cdate="2030-03-17", stage="CONSTRUCTION")
    own = _order(fl.match_name, customer="내고객",
                 extra={"schedule": _with_link(_sd("", "", stage="MEASURE", cdate=None), victim)["schedule"]})
    _link(own, fl)
    client = _client(app, fl)
    for path in (f"/edit/{own}", f"/erp/orders/{own}/mobile"):
        html = _html(client, path)
        assert "피해자김비밀" not in html and "3/17" not in html and _BANNER_TITLE not in html, path
    # 폼 저장이 링크를 그대로 되실어 보내면(바꾸지 않음) 직원이 건 링크는 지워지지 않는다
    assert _put_sd(client, own, _own_sd(own)).status_code == 200
    assert _own_sd(own)["schedule"]["as_visit"]["schedule_link"]["ref_order_id"] == victim
    # 대조군: 모든 주문을 읽는 직원에게는 그대로 보인다
    staff_html = _html(_client(app, _staff("CS")), f"/edit/{own}")
    assert "피해자김비밀" in staff_html and _BANNER_TITLE in staff_html


def test_schedule_link_to_readable_order_still_saved_and_shown(app):
    """대조군: 내 다른 주문을 기준으로 거는 링크는 저장되고 배너에 그 고객명이 나온다."""
    fl = _freelancer()
    own = _order(fl.match_name, customer="내고객")
    mine_too = _order(fl.match_name, customer="내다른고객", cdate="2030-03-20", stage="CONSTRUCTION")
    _link(own, fl)
    _link(mine_too, fl)
    client = _client(app, fl)
    assert _put_sd(client, own, _with_link(_own_sd(own), mine_too)).status_code == 200
    assert _own_sd(own)["schedule"]["as_visit"]["schedule_link"]["ref_order_id"] == mine_too
    assert "내다른고객" in _html(client, f"/edit/{own}")


# --------------------------------------------------------------------------
# R2: structured PUT 으로 정산 차감 지우기 · 취소 표시(모든 직원)
# --------------------------------------------------------------------------
def _deducted_order(fl: SimpleNamespace) -> int:
    ded = {"settlement": {"status": "ISSUE_RAISED", "deductions": [
        {"id": "d1", "department": "SALES", "charge_to_user_id": fl.id, "amount": -300000, "reason": "가짜 하자"}]}}
    return _order(fl.match_name, extra=ded, stage="COMPLETED", cdate="2030-02-10")


@pytest.mark.parametrize("who", ["freelancer", "staff"])
def test_put_cannot_remove_or_void_settlement_deductions(app, who):
    fl = _freelancer()
    fl_id = fl.id
    oid = _deducted_order(fl)
    _link(oid, fl)
    client = _client(app, fl if who == "freelancer" else _staff())
    before = _own_sd(oid)["settlement"]
    voided = dict(before["deductions"][0], voided_at="2030-01-01", voided_by=1, void_reason="가짜")
    for settlement in ({"deductions": []}, {"deductions": [voided]}, None):
        sd = _own_sd(oid)
        if settlement is None:
            sd.pop("settlement", None)  # 빠뜨린 저장
        else:
            sd["settlement"] = settlement
        assert _put_sd(client, oid, sd).status_code == 200
        after = _own_sd(oid)
        assert after["settlement"] == before
        assert sales_deduction_total(after, fl_id) == 300000


def test_put_cannot_introduce_settlement(app):
    """서버에 정산 묶음이 없던 주문에 폼이 만들어 넣는 값도 버린다."""
    staff = _staff()
    oid = _order("남의담당", stage="COMPLETED", cdate="2030-02-10")
    sd = _own_sd(oid)
    sd["settlement"] = {"status": "DONE", "cash_receipt": {"issued": True}}
    assert _put_sd(_client(app, staff), oid, sd).status_code == 200
    assert "settlement" not in _own_sd(oid)


def test_dedicated_deduction_api_still_writes_and_survives_form_save(app):
    """대조군: 전용 차감 API 는 그대로 쓰고, 뒤이은 폼 저장(낡은 사본)이 그 차감을 지우지 않는다."""
    fl = _freelancer()
    fl_id = fl.id
    oid = _order(fl.match_name, stage="COMPLETED", cdate="2030-02-10")
    stale = _own_sd(oid)
    resp = _client(app, _staff("CS")).post(
        f"/api/orders/{oid}/settlement/issue",
        json={"department": "SALES", "amount": 40000, "reason": "가짜 청구", "charge_to_user_id": fl_id})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    assert sales_deduction_total(_own_sd(oid), fl_id) == 40000
    assert _put_sd(_client(app, _staff()), oid, stale).status_code == 200
    assert sales_deduction_total(_own_sd(oid), fl_id) == 40000


# --------------------------------------------------------------------------
# R4: structured PUT 으로 입금 확인 위조 · 되돌리기(모든 직원)
# --------------------------------------------------------------------------
def test_put_cannot_forge_payment_confirmation_but_amounts_still_save(app):
    staff = _staff()
    oid = _order("남의담당")
    sd = _own_sd(oid)
    sd["payment"] = {"deposit": 100000, "discount": 5000, **_CONFIRM_FORGERY,
                     "balance_confirmed": True, "balance_method": "카드"}
    assert _put_sd(_client(app, staff), oid, sd).status_code == 200
    pay = _own_sd(oid)["payment"]
    assert pay["deposit"] == 100000 and pay["discount"] == 5000  # 나머지 결제 칸은 그대로 저장된다
    for key in ("deposit_confirmed", "deposit_confirmed_by", "deposit_confirmed_by_user_id",
                "balance_confirmed", "balance_method"):
        assert not pay.get(key), key


def test_payment_confirm_api_writes_and_stale_form_save_keeps_it(app):
    """대조군: 결제 확인 API 는 그대로 쓰고, 확인 전 사본을 실은 폼 저장이 확인을 되돌리지 않는다."""
    accountant = _staff("ACCOUNTING")
    accountant_id, accountant_name = accountant.id, accountant.name
    oid = _order("남의담당")
    stale = _own_sd(oid)
    stale["payment"] = {"deposit": 70000, "deposit_confirmed": False, "deposit_confirmed_by": None}
    resp = _client(app, accountant).post(f"/api/orders/{oid}/payment-confirm",
                                         json={"type": "deposit", "confirmed": True})
    assert resp.status_code == 200 and resp.get_json()["payment"]["deposit_confirmed"] is True
    assert _put_sd(_client(app, _staff()), oid, stale).status_code == 200
    pay = _own_sd(oid)["payment"]
    assert pay["deposit"] == 70000
    assert pay["deposit_confirmed"] is True
    assert pay["deposit_confirmed_by_user_id"] == accountant_id
    assert pay["deposit_confirmed_by"] == accountant_name


def _new_draft(client) -> int:
    resp = client.post("/api/orders/erp/draft", json={}, headers={"Origin": "http://localhost"})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    return int(resp.get_json()["order_id"])


def _registration_sd(manager: str) -> dict:
    sd = _sd(manager, "새고객", stage="RECEIVED", cdate=None)
    sd["payment"] = {"deposit": 50000, **_CONFIRM_FORGERY}
    return sd


def test_first_registration_keeps_confirm_but_server_stamps_who(app):
    """대조군: 새 주문 화면은 저장 전에 결제 확인을 누르고 첫 등록에 싣는다 — 받되 누가는 서버가 찍는다."""
    staff = _staff()
    staff_id, staff_name = staff.id, staff.name
    client = _client(app, staff)
    draft_id = _new_draft(client)
    assert _put_sd(client, draft_id, _registration_sd("남의담당")).status_code == 200
    pay = _own_sd(draft_id)["payment"]
    assert pay["deposit_confirmed"] is True and pay["deposit"] == 50000
    assert pay["deposit_confirmed_by_user_id"] == staff_id
    assert pay["deposit_confirmed_by"] == staff_name
    assert pay["deposit_confirmed_at"] != _CONFIRM_FORGERY["deposit_confirmed_at"]


def test_freelancer_first_registration_confirms_payment_like_staff(app):
    """D27(11-07): 프리랜서도 자기 주문은 회사 영업 직원과 같다 — 첫 등록의 입금 확인을 싣고, 누가 했는지는 서버가 찍는다."""
    fl = _freelancer()
    client = _client(app, fl)
    draft_id = _new_draft(client)
    assert _put_sd(client, draft_id, _registration_sd(fl.match_name)).status_code == 200
    pay = _own_sd(draft_id)["payment"]
    assert pay["deposit"] == 50000
    assert pay.get("deposit_confirmed") is True and pay.get("deposit_confirmed_by_user_id") == fl.id


# --------------------------------------------------------------------------
# R6: ERP 초안 토큰으로 남의 초안에 묶이기
# --------------------------------------------------------------------------
def _draft_call(client, method: str, path: str, **kwargs):
    return getattr(client, method)(path, headers={"Origin": "http://localhost"}, **kwargs)


def test_other_users_draft_token_is_not_attachable(app):
    owner = _staff()
    owner_client = _client(app, owner)
    token = f"tok-{next(_seq)}-redteam"
    created = _draft_call(owner_client, "post", "/api/orders/erp/draft", json={"draft_token": token}).get_json()
    victim_draft = created["order_id"]
    before = _own_sd(victim_draft)

    intruder = _staff()
    got = _draft_call(_client(app, intruder), "get", f"/api/orders/erp/draft?draft_token={token}").get_json()
    assert got["success"] and got["draft"] is None
    _draft_call(_client(app, intruder), "post", "/api/orders/erp/draft/discard", json={"draft_token": token})
    made = _draft_call(_client(app, intruder), "post", "/api/orders/erp/draft",
                       json={"draft_token": token}).get_json()
    assert made["order_id"] != victim_draft and made["reused"] is False  # 남의 초안 대신 새 초안
    autosave = _draft_call(_client(app, intruder), "post", "/api/orders/erp/draft/autosave", json={
        "draft_token": token, "structured_data": _sd("침입자", "침입고객", stage="RECEIVED", cdate=None)}).get_json()
    assert autosave["success"] and autosave["order_id"] == made["order_id"]  # 토큰은 내 초안만 찾는다

    db_session.expire_all()
    victim = db_session.get(Order, victim_draft)
    assert victim.status == "DRAFT" and victim.deleted_at is None
    assert _own_sd(victim_draft) == before

    # 대조군: 같은 사람은 새 세션(다른 탭 · 재로그인)에서도 같은 토큰으로 내 초안을 다시 잡는다
    again = _draft_call(_client(app, owner), "post", "/api/orders/erp/draft", json={"draft_token": token}).get_json()
    assert again == {"success": True, "order_id": victim_draft, "reused": True}


# --------------------------------------------------------------------------
# R7: 마법사 등록 중복 확인이 남의 주문 번호를 돌려줌
# --------------------------------------------------------------------------
def _wizard_submit(client, key: str, customer: str):
    payload = {"schema_version": 1, "step": 4, "data": {
        "customer_name": customer, "phone": "010-3269-0000", "address": "가짜구 가짜로 2",
        "items": [{"product_name": "가짜장"}], "schedule": {}}}
    resp = client.post("/api/erp/order-draft/submit", json={"draft_key": key, "payload": payload},
                       headers={"Origin": "http://localhost"})
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    return resp.get_json()["data"]


def test_wizard_duplicate_check_ignores_other_users_orders(app, monkeypatch):
    monkeypatch.setenv("FOMS_WIZARD_NEW_ORDER_ENABLED", "true")
    key, customer = f"new.redteam-{next(_seq)}", f"중복확인고객{next(_seq)}"
    owner_client = _client(app, _staff())
    first = _wizard_submit(owner_client, key, customer)

    other = _wizard_submit(_client(app, _staff()), key, customer)
    assert "already_submitted" not in other and other["order_id"] != first["order_id"]

    # 대조군: 내가 같은 초안을 다시 누르면 먼저 만든 내 주문 번호가 돌아온다
    assert _wizard_submit(owner_client, key, customer) == {"order_id": first["order_id"],
                                                           "already_submitted": True}


# --------------------------------------------------------------------------
# R9: 되채우기 CREATOR 가 손님 값 OrderDraft.order_id 를 믿음
# --------------------------------------------------------------------------
def test_creator_links_ignore_wizard_draft_order_id(app):
    fl = _freelancer()
    fl_id = fl.id
    victim = _order(customer="남의주문고객")
    mine = _order(fl.match_name, customer="내가만든고객")
    when = datetime.datetime(2030, 2, 1, 12, 0)
    db_session.add(OrderDraft(user_id=fl_id, draft_key=f"new.r9-{next(_seq)}", payload={}, order_id=victim,
                              created_at=when, updated_at=when, expires_at=when + datetime.timedelta(days=30)))
    db_session.add(OrderEvent(order_id=mine, event_type="ORDER_CREATED", payload={},
                              created_by_user_id=fl_id, created_at=when))
    db_session.commit()

    links = creator_links(db_session, [victim, mine], load_link_snapshot(db_session))
    assert victim not in links
    # 대조군: 생성 이벤트 작성자는 그대로 CREATOR 다
    assert links.get(mine) == {(fl_id, REL_CREATOR)}


# --------------------------------------------------------------------------
# R3 추적: 대표 담당 · 담당 명단 바꾸기가 "본인 수정" 기록에 잡힌다(막기는 겹 4 — 별도 시험)
# --------------------------------------------------------------------------
def test_manager_paths_are_tracked_as_self_edits():
    assert {"parties.manager.name", "parties.manager.names"} <= set(SELF_EDIT_PATHS)
    core = (_ROOT / "static" / "js" / "settlement" / "commission-core.js").read_text(encoding="utf-8")
    labels = core.split("C.SELF_EDIT_LABELS = {")[1].split("};")[0]
    for path in SELF_EDIT_PATHS:
        assert f"'{path}':" in labels, path
