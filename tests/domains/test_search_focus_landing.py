"""검색 카드 딥링크(?q=&focus_order=) 착지 — drawing / production 단계 큐.

measurement는 test_erp_measurement_mobile_render.py가 커버한다. 여기선 deep-link SSOT가
누락됐던 도면 작업실이 날짜창/페이지/q 필터와 무관하게 단건을 착지시키는지, 생산 단계는 첫 화면 ``?order=`` 로 가는지 검증.
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


def _orders_order(customer_name: str) -> Order:
    order = Order(
        received_date="2026-05-30",
        customer_name=customer_name,
        phone="010-7777-8888",
        address="Seoul",
        product="붙박이",
        status="RECEIVED",
        is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": customer_name}},
            "workflow": {"stage": "RECEIVED"},
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_orders_dashboard_focus_order_lands_despite_nonmatching_q(login) -> None:
    order_id = _orders_order("주문큐포커스고객").id

    # 컨트롤: 비매칭 q는 결과 0 → 목록에 없다(또는 history로 리다이렉트).
    control = login.get("/erp/dashboard?view=queue&q=zzz없는검색어")
    assert "주문큐포커스고객" not in control.get_data(as_text=True)

    # 검색 카드 딥링크: focus_order로 q·60일창·페이지와 무관하게 단건 착지(+history 리다이렉트 차단).
    focused = login.get(f"/erp/dashboard?view=queue&q=zzz없는검색어&focus_order={order_id}")
    assert focused.status_code == 200
    assert "주문큐포커스고객" in focused.get_data(as_text=True)


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


def test_production_search_link_lands_on_home_order(client, app) -> None:
    """생산 단계 검색 카드는 옛 보드(``?q=&focus_order=``)가 아니라 첫 화면 ``?order=<id>`` 로 간다 — 옛 보드는 2026-11-27
    없앴다(옛 보드 없애기 설계서 §5-1). 검색어는 첫 화면이 읽지 않는다. 그 주소를 열면 그 주문이 보인다."""
    from foms.services.erp_order_deeplink import build_order_queue_focus_href
    from tests.support.production_access_support import login as login_as, make_user

    login_as(client, make_user("search_focus_cs", "STAFF", "CS"))
    order = _production_order("생산포커스고객")
    with app.test_request_context("/"):
        href = build_order_queue_focus_href(order, search_query="zzz없는검색어")
    assert href == f"/erp/production/home?order={order.id}"
    focused = client.get(href)
    assert focused.status_code == 200
    assert "생산포커스고객" in focused.get_data(as_text=True)
