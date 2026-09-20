"""F9 — 주문 SALES owner(STAFF) 가 도면 수령 확정을 할 수 있다(2026-09-20).

주문 생성(create_order — /add 두 경로가 부르는 바로 그 함수)은 owner 를
OrderAssignment(domain='SALES', source='INITIAL_OWNER') 행에만 남기고
`assignments.sales_assignee_user_ids` 는 비워 둔다. 예전 권한 블록은 그 JSONB 배열과
이름 대조만 봐서 owner STAFF 가 403 을 받았다. 이제 ID-row 대조가 이름 대조보다 먼저다.
"""

from __future__ import annotations

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.orders.order_create import create_order
from models import Order, OrderAssignment, User

_DRAWING_SD = {
    "workflow": {"stage": "DRAWING"},
    "drawing_status": "TRANSFERRED",
    "drawing_current_files": [],
    "drawing_transfer_history": [{"action": "TRANSFER", "files": []}],
}


def _make_user(username, *, role="STAFF", team="SALES", name=None):
    user = User(
        username=username,
        password=generate_password_hash("pass"),
        role=role,
        team=team,
        name=name or username,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _create_owned_order(owner: User) -> int:
    """/add 가 부르는 create_order 로 owner 명의 주문을 만든다(DRAWING·전달된 도면)."""
    order = create_order(
        db_session,
        actor_user_id=owner.id,
        owner_user_id=owner.id,
        order_fields=dict(
            received_date="2026-09-20",
            customer_name="오너 고객",
            phone="010-0000-0000",
            address="서울",
            product="붙박이장",
            status="DRAWING",
        ),
        structured_data=dict(_DRAWING_SD),
        is_erp_order=True,
    )
    db_session.commit()
    return order.id


def _sales_rows(order_id: int) -> list[OrderAssignment]:
    return (
        db_session.query(OrderAssignment)
        .filter(OrderAssignment.order_id == order_id, OrderAssignment.domain == "SALES")
        .all()
    )


def _confirm(client, order_id: int):
    return client.post(f"/api/orders/{order_id}/confirm-drawing-receipt", json={})


def test_owner_STAFF_는_JSONB_배정이_비어_있어도_수령_확정_200(client):
    owner = _make_user("f9_owner")
    order_id = _create_owned_order(owner)

    # 회귀 조건 명시: create_order 는 JSONB 배열을 채우지 않고 OrderAssignment 행만 남긴다.
    order = db_session.get(Order, order_id)
    assert not (order.structured_data.get("assignments") or {}).get("sales_assignee_user_ids")
    assert [r.user_id for r in _sales_rows(order_id)] == [owner.id]
    assert _sales_rows(order_id)[0].source == "INITIAL_OWNER"

    _login(client, owner)
    res = _confirm(client, order_id)
    assert res.status_code == 200, res.get_json()
    assert res.get_json()["success"] is True
    db_session.expire_all()
    assert db_session.get(Order, order_id).structured_data["drawing_status"] == "CONFIRMED"


def test_대조군_다른_SALES_STAFF_는_403(client):
    owner = _make_user("f9_owner2")
    other = _make_user("f9_other")
    order_id = _create_owned_order(owner)

    _login(client, other)
    res = _confirm(client, order_id)
    assert res.status_code == 403
    assert "지정된 영업 담당자" in res.get_json()["message"]
    db_session.expire_all()
    assert db_session.get(Order, order_id).structured_data["drawing_status"] == "TRANSFERRED"


def test_대조군_ADMIN_은_배정과_무관하게_200(client):
    owner = _make_user("f9_owner3")
    admin = _make_user("f9_admin", role="ADMIN", team="CS")
    order_id = _create_owned_order(owner)

    _login(client, admin)
    res = _confirm(client, order_id)
    assert res.status_code == 200, res.get_json()


def test_owner_배정이_해제되면_owner_STAFF_도_403_ID_row_가_정본(client):
    owner = _make_user("f9_owner4")
    order_id = _create_owned_order(owner)
    for row in _sales_rows(order_id):
        row.active = False
    db_session.commit()

    _login(client, owner)
    res = _confirm(client, order_id)
    assert res.status_code == 403
    assert "지정된 영업 담당자" in res.get_json()["message"]


def test_이름_대조_fallback_은_그대로_배정_행_없이_manager_name_이_같으면_200(client):
    staff = _make_user("f9_named", name="이름담당")
    order = Order(
        received_date="2026-09-20",
        customer_name="이름 고객",
        phone="010-0000-0000",
        address="서울",
        product="붙박이장",
        status="DRAWING",
        manager_name="이름담당",
        is_erp_order=True,
        structured_data=dict(_DRAWING_SD),
        erp_stage_code="DRAWING",
    )
    db_session.add(order)
    db_session.commit()
    assert _sales_rows(order.id) == []

    _login(client, staff)
    res = _confirm(client, order.id)
    assert res.status_code == 200, res.get_json()


def test_add_폼으로_STAFF_가_만든_ERP_주문도_owner_가_수령_확정_200(client):
    """/add 의 ERP_ORDER 경로로 만든 주문 — 폼이 create_order 를 거쳐 owner 행을 남기는지 실증."""
    owner = _make_user("f9_form_owner")
    owner_id = owner.id  # 요청 사이클이 세션을 닫으면 ORM 객체가 분리된다 — id 를 미리 잡는다.
    _login(client, owner)
    res = client.post(
        "/add",
        data={
            "create_mode": "ERP_ORDER",
            "received_date": "2026-09-20",
            "erp_customer_name": "폼 고객",
            "erp_customer_phone": "010-1111-2222",
            "erp_address": "서울 폼동",
            "erp_product": "붙박이장",
            "status": "RECEIVED",
        },
    )
    assert res.status_code in (302, 303), res.status_code
    order = (
        db_session.query(Order)
        .filter(Order.customer_name == "폼 고객")
        .order_by(Order.id.desc())
        .first()
    )
    assert order is not None, "폼 POST 가 주문을 만들지 못했다"
    assert [r.user_id for r in _sales_rows(order.id)] == [owner_id]

    # 도면 전달 상태로 올려 놓는다(수령 확정 상태 가드 통과용).
    sd = dict(order.structured_data or {})
    sd.update(_DRAWING_SD)
    order.structured_data = sd
    order.status = "DRAWING"
    db_session.commit()
    order_id = order.id

    res = _confirm(client, order_id)
    assert res.status_code == 200, res.get_json()
    db_session.expire_all()
    assert db_session.get(Order, order_id).structured_data["drawing_status"] == "CONFIRMED"
