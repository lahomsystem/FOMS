"""생산 보드 [제작 시작] 막힘 문구의 영업 담당 이름 — 배정 표(order_assignments)가 정본.

운영 증상(2026-10-22, 주문 5625 김나윤): 영업 담당(양산지사)이 배정 표에만 있고
``structured_data.assignments.sales_assignee_user_ids`` 는 비어 있어, 문구가
"영업 담당이 아직 수령 확정하지 않았어요" 처럼 이름 없이 나왔다.
"""
from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.erp_display import get_today_kst
from foms.services.production_drawing_gate_display import attach_production_drawing_gate
from models import Order, OrderAssignment, User


def _user(username: str, name: str) -> User:
    user = User(
        username=username, password=generate_password_hash("x"), role="MANAGER",
        team="SALES", name=name, is_active=True,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _order(sd_extra: dict | None = None) -> Order:
    sd = {"workflow": {"stage": "PRODUCTION"}, "drawing_status": "TRANSFERRED", **(sd_extra or {})}
    order = Order(
        received_date=get_today_kst().isoformat(), customer_name="이름 고객", phone="010-0000-0000",
        address="Seoul", product="붙박이장", status="PRODUCTION", is_erp_order=True,
        structured_data=sd, erp_stage_code="PRODUCTION",
    )
    db_session.add(order)
    db_session.flush()
    return order


def _waiting_row(order: Order) -> dict:
    return {"id": order.id, "stage": "제작대기", "is_sales_approved": True}


def test_block_reason_names_sales_from_assignment_table(app):
    sales = _user("gate_name_sales", "양산지사")
    order = _order()
    db_session.add(OrderAssignment(order_id=order.id, domain="SALES", user_id=sales.id,
                                   source="TEAM_REPLACE", active=True, assigned_by_user_id=sales.id))
    db_session.commit()
    row = _waiting_row(order)

    attach_production_drawing_gate(db_session, [row], {order.id: order})

    assert row["production_start_blocked"] is True
    assert "영업 담당(양산지사)" in row["production_start_block_reason"]


def test_block_reason_falls_back_to_structured_ids_without_assignment_rows(app):
    legacy = _user("gate_name_legacy", "옛영업")
    order = _order({"assignments": {"sales_assignee_user_ids": [legacy.id]}})
    db_session.commit()
    row = _waiting_row(order)

    attach_production_drawing_gate(db_session, [row], {order.id: order})

    assert "영업 담당(옛영업)" in row["production_start_block_reason"]
