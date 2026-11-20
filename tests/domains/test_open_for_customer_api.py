"""새 주문 안내 읽기 API ``GET /api/orders/open-for-customer`` (설계서 2026-11-20 6.1 · M17).

완료 기준: 본사 직원은 200 + ``{success, data: {orders, more}, error}`` · 주문 줄에 PC · 휴대폰 주소가 붙음 ·
자기 초안 줄(``exclude_order_id``)은 빠짐 · 켜진 프리랜서 403 · 협력사 403 · 로그인 없으면 못 읽음.
"""

from __future__ import annotations

from tests.domains.test_auth_finance import _login, _make_user
from tests.domains.test_open_order_lookup import HOME, HOME_SHORT, OTHER, OTHER_DIGITS, PHONE, add_order
from tests.security.test_freelancer_gate import FREELANCER_DENIED_MSG, _freelancer
from tests.security.test_partner_gate import _DENIED_MSG as PARTNER_DENIED_MSG
from tests.security.test_partner_gate import _org
from tests.security.test_partner_gate import _user as _partner_user

URL = "/api/orders/open-for-customer"


def test_staff_gets_open_orders_with_links(client):
    order = add_order(construction=("2026-11-17",))
    order_id = order.id
    add_order(stage="COMPLETED")  # 대조군: 완료 주문
    _login(client, _make_user("STAFF", "SALES"))

    response = client.get(URL, query_string={"phone": PHONE, "name": "합성고객", "address": ""})

    assert response.status_code == 200
    body = response.get_json()
    assert set(body) == {"success", "data", "error"}
    assert body["success"] is True and body["error"] is None
    assert body["data"]["more"] == 0
    assert body["data"]["orders"] == [{
        "order_id": order_id, "stage_code": "PRODUCTION", "stage_label": "생산",
        "construction_dates": ["2026-11-17"], "address": "합성시 가상구 다른로 1", "customer_name": "합성고객",
        "reason": "phone", "url": f"/edit/{order_id}?open=erp-order", "mobile_url": f"/erp/orders/{order_id}/mobile",
    }]


def test_more_counts_orders_beyond_three(client):
    for _ in range(4):
        add_order(stage="MEASURE")
    _login(client, _make_user("MANAGER", "CS"))

    data = client.get(URL, query_string={"phone": PHONE}).get_json()["data"]

    assert len(data["orders"]) == 3 and data["more"] == 1


def test_exclude_order_id_drops_own_draft_row_and_address_axis_works(client):
    mine = add_order(stage="RECEIVED", address=HOME)
    family = add_order(name="가족", phone=OTHER, digits=OTHER_DIGITS, address=HOME)
    mine_id, family_id = mine.id, family.id
    _login(client, _make_user("ADMIN", None))

    data = client.get(URL, query_string={"phone": PHONE, "address": HOME_SHORT, "exclude_order_id": mine_id}).get_json()["data"]

    assert [(row["order_id"], row["reason"]) for row in data["orders"]] == [(family_id, "address")]


def test_empty_input_returns_empty_list(client):
    add_order()
    _login(client, _make_user("STAFF", "CS"))

    body = client.get(URL).get_json()

    assert body == {"success": True, "data": {"orders": [], "more": 0}, "error": None}


def test_freelancer_is_denied(client):
    add_order()
    _login(client, _freelancer())

    response = client.get(URL, query_string={"phone": PHONE})

    assert response.status_code == 403
    body = response.get_json()
    assert body["success"] is False and FREELANCER_DENIED_MSG in str(body)
    assert "orders" not in str(body)


def test_partner_is_denied(client):
    add_order()
    org = _org("합성협력사-안내")
    _login(client, _partner_user(role="PARTNER", team=None, org=org))

    response = client.get(URL, query_string={"phone": PHONE})

    assert response.status_code == 403
    body = response.get_json()
    assert body["success"] is False and body["error"] == PARTNER_DENIED_MSG
    assert body["data"] is None


def test_anonymous_cannot_read(client):
    add_order()

    response = client.get(URL, query_string={"phone": PHONE})

    assert response.status_code in (302, 401)
    assert "order_id" not in response.get_data(as_text=True)


def test_viewer_role_is_denied(client):
    add_order()
    _login(client, _make_user("VIEWER", None))

    response = client.get(URL, query_string={"phone": PHONE})

    assert response.status_code in (302, 403)
    assert "order_id" not in response.get_data(as_text=True)
