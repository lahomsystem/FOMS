"""생산 보기 · 쓰기 · 메뉴 시험의 공용 준비물(설계서 2026-11-21-production-pc-viewer §5 · §9 · §11). 이름 · 번호는 가짜 값이다."""
from __future__ import annotations

from types import SimpleNamespace

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst
from models import Order, User

# --------------------------------------------------------------------------- #
# 사람 표 — (이름, role, team, 쓰기, 보기). 보기 열은 2026-11-21 보는 팀(도면 · 시공 · 출고 포함) 기준
# --------------------------------------------------------------------------- #
PEOPLE = [
    ("admin_noteam", "ADMIN", None, True, True),
    ("admin_sales", "ADMIN", "SALES", True, True),
    ("prod_staff", "STAFF", "PRODUCTION", True, True),
    ("prod_manager", "MANAGER", "PRODUCTION", True, True),
    ("cs_staff", "STAFF", "CS", False, True),
    ("cs_manager", "MANAGER", "CS", False, True),
    ("acct_staff", "STAFF", "ACCOUNTING", False, True),
    ("sales_staff", "STAFF", "SALES", False, True),
    ("sales_manager", "MANAGER", "SALES", False, True),
    ("measure_staff", "STAFF", "MEASURE", False, True),
    ("drawing_staff", "STAFF", "DRAWING", False, True),
    ("construction_staff", "STAFF", "CONSTRUCTION", False, True),
    ("shipment_staff", "STAFF", "SHIPMENT", False, True),
    ("prod_viewer", "VIEWER", "PRODUCTION", False, True),
    ("noteam_staff", "STAFF", None, False, False),
]

#: 생산 쓰기 API 여덟(관리자 · 생산팀만). [확인했어요](change-ack)는 쓰기가 아니라 개인 확인 기록이라 따로 — 보는 사람 모두(§13 결정 5).
WRITE_ENDPOINTS = [
    ("start", {}),
    ("complete", {}),
    ("rework", {"reason": "가짜 사유"}),
    ("cancel", {}),
    ("uncomplete", {}),
    ("steps", {"key": "cut", "done": True}),
    ("defect", {"reason": "파손"}),
    ("hold", {"active": True, "reason": "가짜 사유"}),
]
ACK_PATH = "change-ack"


def can_ack(role: str, view: bool) -> bool:
    """사람 표의 [확인했어요] 열 — 보기 열이 참이고 조회 전용(VIEWER)이 아니면 참(엔진 F-01 과 같은 답)."""
    return view and role != "VIEWER"



def ns(role, team, *, partner_org_id=None, is_active=True):
    return SimpleNamespace(id=990001, role=role, team=team, partner_org_id=partner_org_id, is_active=is_active, name="가짜")



def make_user(username: str, role: str, team: str | None, *, partner_org_id: int | None = None,
              lead: bool | None = None) -> User:
    user = User(username=username, password=generate_password_hash("pw"), role=role, team=team,
                name=f"가짜{username}", is_active=True, partner_org_id=partner_org_id, production_lead=lead)
    db_session.add(user)
    db_session.commit()
    return user


def login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def make_order(customer: str = "가짜생산고객", *, construction: str | None = None) -> Order:
    today = get_today_kst().isoformat()
    sd = {
        "parties": {"customer": {"name": customer}, "manager": {"name": "가짜담당"}},
        "workflow": {"stage": "PRODUCTION"},
        "items": [{"product_name": "가짜장", "spec_width": "900", "quantity": 1}],
    }
    if construction:
        sd["schedule"] = {"construction": {"date": construction}}
    order = Order(
        received_date=today, customer_name=customer, phone="010-0000-0000", address="가짜시", product="가짜장",
        status="PRODUCTION", manager_name="가짜담당", is_erp_order=True, structured_data=sd,
        erp_stage_code="PRODUCTION", erp_construction_date=construction or None,
    )
    db_session.add(order)
    db_session.commit()
    return order


