"""프리랜서 생산 첫 화면 시험 준비물 — tests/security/test_freelancer_production_home.py 가 쓴다.

가짜 계정 넷(켜진 프리랜서 가 · 나, 회사 영업 직원, 꺼진 프리랜서)과 가짜 주문(내 것 1 · 남의 것 4 · 취소 묘비 3)을 만든다.
주문 번호 · 전화 끝자리는 화면의 다른 숫자와 겹치지 않게 크게 · 서로 다르게 준다 — 새는지 볼 때 앞뒤가 숫자가 아닌 자리만 센다.
모든 이름 · 번호는 가짜 값이다.
"""
from __future__ import annotations

import datetime
import re
from types import SimpleNamespace
from typing import Any, Iterable

from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import Order, OrderFreelancerLink, ProductionRun
from tests.domains.test_auth_finance import _login, _make_user

HOME = "/erp/production/home"
#: 기기 쿠키 — PC(마우스) · 태블릿 가로(터치 + 넓은 창) · 폰(터치 + 좁은 창 + 화면 긴 변 992 미만).
DEVICES: dict[str, dict[str, str]] = {
    "pc": {"foms_ptr": "fine"},
    "tablet": {"foms_ptr": "coarse", "foms_vw": "wide", "foms_scr": "1280"},
    "phone": {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "844"},
}
SHELL = {"X-FOMS-ERP-SHELL": "1"}
MATCH_A, MATCH_B, MATCH_OFF = "가짜생산프리가", "가짜생산프리나", "가짜생산프리꺼짐"
#: 프리랜서 가의 계정 표시 이름 — 이 이름이 담당인 주문은 남의 주문이다(연결 표만 본다).
NAME_A = "가짜영업계정가"


def tomorrow() -> str:
    return (get_today_kst() + datetime.timedelta(days=1)).isoformat()


def named_user(role: str, team: str | None, name: str, **columns: Any) -> SimpleNamespace:
    """계정을 만들고 값만 담아 돌려준다(요청이 끝나면 세션이 닫혀 ORM 객체는 못 읽는다)."""
    user = _make_user(role, team)
    user.name = name
    for key, value in columns.items():
        setattr(user, key, value)
    db_session.commit()
    return SimpleNamespace(id=user.id, username=user.username, role=role, team=team, name=name, partner_org_id=None)


def designate(user: Any, match: str, *, active: bool = True) -> None:
    save_freelancer(db_session, user.id, {"match_name": match, "start_month": "2020-01", "tax_type": "NONE",
                                          "active": active},
                    base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()


def link(order_id: int, user: Any) -> None:
    """연결 줄이 없으면 만든다(저장 훅이 이미 만든 줄은 그대로)."""
    if not db_session.query(OrderFreelancerLink).filter_by(order_id=order_id, user_id=user.id).first():
        db_session.add(OrderFreelancerLink(order_id=order_id, user_id=user.id, relation="MANAGER_PRIMARY"))
        db_session.commit()


def linked_order_ids(user: Any) -> set[int]:
    db_session.expire_all()
    return {row.order_id for row in db_session.query(OrderFreelancerLink).filter_by(user_id=user.id).all()}


def make_order(oid: int, customer: str, tail: str, *, manager: str, off: int = 1, stage: str = "PRODUCTION",
               deleted: bool = False, extra: dict | None = None) -> SimpleNamespace:
    """가짜 주문 하나. 생산 단계면 제작 회차를 열어 '내 공정' 재단 줄에 선다. 도면 1장(도면 카드 · PC 도면 창 칸이 그려지게)."""
    today = get_today_kst()
    day = (today + datetime.timedelta(days=off)).isoformat()
    phone, address = f"010-5550-{tail}", f"가짜시 가짜구 {tail}번길"
    sd = {
        "parties": {"manager": {"name": manager}, "customer": {"name": customer, "phone": phone},
                    "orderer": {"name": "라홈"}},
        "site": {"address_full": address},
        "schedule": {"construction": {"date": day}},
        "workflow": {"stage": stage},
        "items": [{"product_name": "가짜장", "spec_width": "900", "quantity": 1}],
        "drawing_current_files": [{"key": f"orders/{oid}/drawing/d0.png", "filename": f"{customer}-도면.png"}],
        "production": {"steps": []},
        **(extra or {}),
    }
    db_session.add(Order(
        id=oid, received_date=today.isoformat(), customer_name=customer, phone=phone, address=address, product="가짜장",
        status="DELETED" if deleted else stage, manager_name=manager, is_erp_order=True, structured_data=sd,
        erp_stage_code=stage, erp_construction_date=day,
        deleted_at=f"{today.isoformat()} 12:00:00" if deleted else None,
    ))
    db_session.commit()
    if stage == "PRODUCTION" and not deleted:
        db_session.add(ProductionRun(order_id=oid, status="IN_PROGRESS", steps=[], defects=[], is_current=True))
        db_session.commit()
    return SimpleNamespace(id=oid, customer=customer, tail=tail, phone=phone)


def seed_world() -> SimpleNamespace:
    """계정 넷 + 주문. 프리랜서 가의 연결 표 = 내 주문 1 + 내 묘비 1 뿐(함정 주문 둘은 연결이 없다)."""
    fl_a = named_user("STAFF", "SALES", NAME_A)
    designate(fl_a, MATCH_A)
    fl_b = named_user("STAFF", "SALES", "가짜영업계정나")
    designate(fl_b, MATCH_B)
    staff = named_user("STAFF", "SALES", "가짜회사영업")
    off = named_user("STAFF", "SALES", "가짜꺼진프리")
    designate(off, MATCH_OFF, active=False)

    own = make_order(8800101, "가짜고객가", "7391", manager=MATCH_A)
    own_tomb = make_order(8800111, "가짜묘비가", "7392", manager=MATCH_A, deleted=True)
    b_order = make_order(8800202, "가짜고객나", "8462", manager=MATCH_B)
    staff_order = make_order(8800303, "가짜고객다", "9573", manager=NAME_A)  # 함정: 담당 이름 = 가의 계정 이름
    others = [
        b_order,
        make_order(8800212, "가짜옛손님나", "8463", manager=MATCH_B, off=-40),  # 지난 출고일 묶음(캡 · 총계 쪽)
        staff_order,
        make_order(8800313, "가짜고객라", "9574", manager="다른담당", stage="CONSTRUCTION",  # 함정: 영업 담당 id 칸
                   extra={"assignments": {"sales_assignee_user_ids": [fl_a.id]}}),
    ]
    other_tombs = [
        make_order(8800422, "가짜묘비나", "8464", manager=MATCH_B, deleted=True),
        make_order(8800433, "가짜묘비다", "9575", manager="다른담당", deleted=True),
    ]
    for order in (own, own_tomb):
        link(order.id, fl_a)
    for order in (others[0], others[1], other_tombs[0]):
        link(order.id, fl_b)
    assert linked_order_ids(fl_a) == {own.id, own_tomb.id}
    return SimpleNamespace(fl_a=fl_a, fl_b=fl_b, staff=staff, off=off, own=own, own_tomb=own_tomb, b_order=b_order,
                           staff_order=staff_order, others=others, other_tombs=other_tombs,
                           foreign=others + other_tombs)


def client_for(app: Any, user: Any, device: str | None = None) -> Any:
    client = app.test_client()
    _login(client, user)
    for key, value in DEVICES.get(device or "", {}).items():
        client.set_cookie(key, value, domain="localhost")
    return client


def leaks(text: str, orders: Iterable[Any]) -> list[tuple[str, str]]:
    """``text`` 에 실린 그 주문들의 글 — (고객 이름, 무엇). 번호 · 전화 끝 네 자리는 앞뒤가 숫자가 아닌 자리만 센다."""
    found: list[tuple[str, str]] = []
    for order in orders:
        if order.customer in text:
            found.append((order.customer, "이름"))
        for digits, what in ((order.tail, "전화 끝자리"), (str(order.id), "주문 번호")):
            if re.search(rf"(?<!\d){digits}(?!\d)", text):
                found.append((order.customer, what))
    return found
