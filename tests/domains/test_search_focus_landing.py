"""검색 카드 딥링크(?q=&focus_order=) 착지 — drawing / production 단계 큐.

measurement는 test_erp_measurement_mobile_render.py가 커버한다. 여기선 deep-link SSOT가
누락됐던 도면 작업실·생산 대시보드가 날짜창/페이지/q 필터와 무관하게 단건을 착지시키는지 검증.
"""

from db import db_session
from models import Order


def _drawing_order(customer_name: str) -> Order:
    order = Order(
        received_date="2026-05-30",
        customer_name=customer_name,
        phone="010-3333-4444",
        address="Seoul",
        product="붙박이",
        status="DRAWING",
        erp_stage_code="DRAWING",
        is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": customer_name}},
            "workflow": {"stage": "DRAWING"},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def _production_order(customer_name: str) -> Order:
    order = Order(
        received_date="2026-05-30",
        customer_name=customer_name,
        phone="010-5555-6666",
        address="Seoul",
        product="붙박이",
        status="PRODUCTION",
        erp_stage_code="PRODUCTION",
        is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": customer_name}},
            "workflow": {"stage": "PRODUCTION"},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_drawing_workbench_focus_order_lands_despite_nonmatching_q(login) -> None:
    order_id = _drawing_order("도면포커스고객").id

    # 컨트롤: q가 매치 안 되면 목록에 없다.
    control = login.get("/erp/drawing-workbench?q=zzz없는검색어")
    assert control.status_code == 200
    assert "도면포커스고객" not in control.get_data(as_text=True)

    # 검색 카드 딥링크: focus_order로 q와 무관하게 단건 착지.
    focused = login.get(f"/erp/drawing-workbench?q=zzz없는검색어&focus_order={order_id}")
    assert focused.status_code == 200
    assert "도면포커스고객" in focused.get_data(as_text=True)


def test_production_dashboard_focus_order_lands_despite_nonmatching_q(login) -> None:
    order_id = _production_order("생산포커스고객").id

    control = login.get("/erp/production/dashboard?q=zzz없는검색어")
    assert control.status_code == 200
    assert "생산포커스고객" not in control.get_data(as_text=True)

    focused = login.get(f"/erp/production/dashboard?q=zzz없는검색어&focus_order={order_id}")
    assert focused.status_code == 200
    assert "생산포커스고객" in focused.get_data(as_text=True)
