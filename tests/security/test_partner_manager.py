"""PARTNER-04: 협력사 주문 담당 = 협력사 직원 · 담당 연락처 · 우리 쪽은 CS 계약.

스펙 docs/specs/2026-10-08-partner-portal_SPEC.md §16. 각 판정에는 같은 조건의 우리 주문(음성 대조군)을 둔다.
"""
from __future__ import annotations

from db import db_session
from models import Order, OrderAssignment, User
from tests.security.partner_fixtures import (  # noqa: F401 — pytest fixture 재노출
    _client,
    _create,
    _to_stage,
    _user,
    world,
)


def _order_id(app, world, partner="partner_a"):
    return _create(app, world[partner]).get_json()["data"]["order_id"]


def _ours(manager_name: str) -> Order:
    order = Order(received_date="2026-10-11", customer_name="우리고객", phone="010-0000-0000", address="a",
                  product="p", manager_name=manager_name,
                  structured_data={"parties": {"manager": {"name": manager_name}}, "workflow": {"stage": "DRAWING"}})
    db_session.add(order)
    db_session.commit()
    return order


def _sales_owner(order_id: int) -> int:
    return (
        db_session.query(OrderAssignment.user_id)
        .filter(OrderAssignment.order_id == order_id, OrderAssignment.domain == "SALES",
                OrderAssignment.active.is_(True))
        .scalar()
    )


# --------------------------------------------------------------------------
# 우리 쪽 = CS 팀
# --------------------------------------------------------------------------
def test_cs_staff_get_sales_domain_on_partner_orders_only(app, world):
    from foms.services.erp_policy import can_modify_domain

    partner_order = db_session.get(Order, _order_id(app, world))
    ours = _ours("영업김")
    cs = db_session.get(User, world["staff"])
    sales = db_session.get(User, world["sales"])
    partner = db_session.get(User, world["partner_a"])
    assert can_modify_domain(cs, partner_order, "SALES_DOMAIN") is True
    assert can_modify_domain(cs, ours, "SALES_DOMAIN") is False  # 대조군: 우리 주문은 그대로
    assert can_modify_domain(sales, partner_order, "SALES_DOMAIN") is False
    assert can_modify_domain(partner, partner_order, "SALES_DOMAIN") is False


def test_drawing_notice_goes_to_cs_for_partner_orders(app, world):
    from foms.api.drawing.erp_orders_drawing import _drawing_notice_target

    # 같은 이름의 우리 직원이 있어도 협력사 주문은 CS 로 간다.
    _user(team="SALES", name="가나 직원")
    assert _drawing_notice_target(db_session, "가나 직원 (가나가구)", partner=True) == ("CS", None, None)
    # 대조군: 우리 주문은 담당 본인.
    assert _drawing_notice_target(db_session, "영업김") == (None, "영업김", None)


def test_same_name_staff_does_not_pick_up_partner_order(app, world):
    from foms.services.erp_display import _can_modify_sales_domain
    from foms.services.erp_permissions import is_order_related_to_user
    from foms.services.order_attachment_permissions import can_manage_order_attachments

    partner_order = db_session.get(Order, _order_id(app, world))
    twin = _user(team="SALES", name="가나 직원")
    assert is_order_related_to_user(partner_order, twin, scope="sales") is False
    assert _can_modify_sales_domain(twin, partner_order, partner_order.structured_data) is False
    with app.test_request_context():
        assert can_manage_order_attachments(twin, partner_order) is False
    # 대조군: 우리 주문은 담당 이름으로 잡힌다.
    ours = _ours("가나 직원")
    assert is_order_related_to_user(ours, twin, scope="sales") is True


# --------------------------------------------------------------------------
# 담당 바꾸기
# --------------------------------------------------------------------------
# 성공 경로(실제 교체)는 SQLite 부분 유니크 함정 때문에 PG 레인 tests/postgres/test_partner_manager_pg.py 가 고정한다.


def test_partner_cannot_hand_order_to_other_company_or_touch_other_orders(app, world):
    order_id = _order_id(app, world)
    client = _client(app, db_session.get(User, world["partner_a"]))
    resp = client.post(f"/api/partner/orders/{order_id}/manager", json={"user_id": world["partner_b"]})
    assert resp.status_code == 400
    resp = client.post(f"/api/partner/orders/{order_id}/manager", json={"user_id": world["staff"]})
    assert resp.status_code == 400
    other = _client(app, db_session.get(User, world["partner_b"]))
    resp = other.post(f"/api/partner/orders/{order_id}/manager", json={"user_id": world["partner_b"]})
    assert resp.status_code == 404
    db_session.expire_all()
    assert _sales_owner(order_id) == world["partner_a"]


def test_staff_form_cannot_change_partner_manager(app, world):
    from foms.services.orders.structured_form_projection import lock_server_owned_keys

    order = db_session.get(Order, _order_id(app, world))
    old = order.structured_data
    new = {"parties": {"manager": {"name": "영업김"}, "orderer": {"name": "가나가구"}}, "source": "PARTNER"}
    ignored = lock_server_owned_keys(old, new)
    assert new["parties"]["manager"] == old["parties"]["manager"]
    assert "parties.manager" in ignored
    # 대조군: 우리 주문은 담당을 바꿀 수 있다.
    ours_new = {"parties": {"manager": {"name": "영업박"}}}
    lock_server_owned_keys({"parties": {"manager": {"name": "영업김"}}}, ours_new)
    assert ours_new["parties"]["manager"] == {"name": "영업박"}


# --------------------------------------------------------------------------
# 연락처 → 도면
# --------------------------------------------------------------------------
def test_wizard_prints_partner_name_and_phone(app, world):
    from foms.services.drawing_wizard_defaults import build_wizard_defaults

    order = db_session.get(Order, _order_id(app, world))
    defaults = build_wizard_defaults(order, order.structured_data, None)
    assert defaults["sales_manager"] == "가나 직원"  # 회사명 꼬리 없이
    assert defaults["manager_phone"] == "1111-2222"  # 도면 표기 규칙: 010 접두 생략
    # 대조군: 우리 주문은 담당 이름 그대로.
    ours = _ours("영업김")
    assert build_wizard_defaults(ours, ours.structured_data, None)["sales_manager"] == "영업김"


def test_phone_change_updates_open_orders_only(app, world):
    open_id = _order_id(app, world)
    done_id = _order_id(app, world)
    _to_stage(done_id, "COMPLETED")
    client = _client(app, db_session.get(User, world["partner_a"]))
    resp = client.post("/api/partner/me/phone", json={"contact_phone": "010 9999 8888"})
    body = resp.get_json()
    assert resp.status_code == 200 and body["data"] == {"contact_phone": "010-9999-8888", "orders_updated": 1}
    db_session.expire_all()
    assert db_session.get(Order, open_id).structured_data["parties"]["manager"]["phone"] == "010-9999-8888"
    assert db_session.get(Order, done_id).structured_data["parties"]["manager"]["phone"] == "010-1111-2222"


def test_phone_rejects_garbage(app, world):
    client = _client(app, db_session.get(User, world["partner_a"]))
    assert client.post("/api/partner/me/phone", json={"contact_phone": "12"}).status_code == 400
    assert db_session.get(User, world["partner_a"]).contact_phone == "010-1111-2222"


def test_admin_sets_partner_user_phone(app, world):
    order_id = _order_id(app, world)
    admin = _client(app, db_session.get(User, world["admin"]))
    resp = admin.post(f"/admin/partners/users/{world['partner_a']}/phone", data={"contact_phone": "01077776666"})
    assert resp.status_code == 302
    db_session.expire_all()
    assert db_session.get(User, world["partner_a"]).contact_phone == "010-7777-6666"
    assert db_session.get(Order, order_id).structured_data["parties"]["manager"]["phone"] == "010-7777-6666"
    # 대조군: 우리 직원 id 로는 못 바꾼다(협력사 계정만).
    admin.post(f"/admin/partners/users/{world['staff']}/phone", data={"contact_phone": "01012341234"})
    db_session.expire_all()
    assert db_session.get(User, world["staff"]).contact_phone is None


def test_partner_pages_show_manager_and_phone(app, world):
    order_id = _order_id(app, world)
    client = _client(app, db_session.get(User, world["partner_a"]))
    detail = client.get(f"/partner/orders/{order_id}").get_data(as_text=True)
    assert "가나 직원 · 010-1111-2222" in detail and "담당 바꾸기" in detail
    home = client.get("/partner").get_data(as_text=True)
    assert 'value="010-1111-2222"' in home

