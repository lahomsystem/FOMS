"""T12 — as_content 쓰기 퇴역 이후의 AS 타임라인 계약.

네 가지를 고정한다.
1) `update_order_field` 는 `as_content`/`as_content_2` 를 더 이상 받지 않는다(400).
   신규 AS 기록은 `POST /api/orders/<id>/as/log` 한 곳으로만 들어온다.
2) 최초 append 가 기존 `as_content` 를 legacy 항목으로 **영구화**한다(표시 시점 lazy
   마이그레이션이 아니라 DB 에 굳는다).
3) 같은 라우트의 `sales_delivery` 토글은 퇴역과 무관하게 살아 있다(회귀 가드).
4) `/erp/as?q=` 검색이 `as_log` 본문까지 본다 — quick-add 로 쌓이는 기록이
   검색 사각지대가 되면 AS 내용 검색은 시간이 갈수록 비어간다(T10 U3).
"""

from __future__ import annotations

from datetime import date

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, User


def _login_as_admin(client, username="as-timeline-contract-admin") -> int:
    """ADMIN/CS 사용자로 로그인하고 id 만 반환(teardown detach 회피)."""
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        team="CS",
        name="AS 타임라인 계약 관리자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    user_id = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = user.username
        sess["role"] = user.role
    return user_id


def _create_as_order(
    *,
    shipment_extra=None,
    as_content_2="<div>2번 내용</div>",
    customer_name="AS 계약 고객",
    status="AS_RECEIVED",
):
    """AS 주문 1건 생성. shipment_extra 가 as_content 를 덮어쓸 수 있다."""
    today = date.today().strftime("%Y-%m-%d")
    shipment = {"as_content": "<div>1번 내용</div>"}
    if as_content_2 is not None:
        shipment["as_content_2"] = as_content_2
    if shipment_extra:
        shipment.update(shipment_extra)
    order = Order(
        received_date=today,
        customer_name=customer_name,
        phone="010-1234-5678",
        address="Seoul",
        product="붙박이장",
        status=status,
        manager_name="Alice",
        as_received_date=today,
        is_erp_order=True,
        structured_data={"workflow": {"stage": status}, "shipment": shipment},
    )
    db_session.add(order)
    db_session.commit()
    return order


# ---------------------------------------------------------------------------
# 1) update_order_field 퇴역
# ---------------------------------------------------------------------------


def test_update_order_field_rejects_as_content(client):
    _login_as_admin(client, username="as-contract-reject-1")
    order = _create_as_order()

    res = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field_name": "as_content", "new_value": "x"},
    )

    assert res.status_code == 400
    assert res.get_json()["success"] is False


def test_update_order_field_rejects_as_content_2(client):
    _login_as_admin(client, username="as-contract-reject-2")
    order = _create_as_order()

    res = client.post(
        "/api/update_order_field",
        json={"order_id": order.id, "field_name": "as_content_2", "new_value": "x"},
    )

    assert res.status_code == 400
    assert res.get_json()["success"] is False


def test_update_order_field_rejection_does_not_touch_structured_data(client):
    """거부는 부작용이 없어야 한다 — 기존 as_content 원문이 그대로 남는다."""
    _login_as_admin(client, username="as-contract-reject-3")
    order = _create_as_order(shipment_extra={"as_content": "<div>보존될 원문</div>"})
    order_id = order.id

    client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field_name": "as_content", "new_value": ""},
    )

    db_session.expire_all()
    shipment = db_session.get(Order, order_id).structured_data["shipment"]
    assert shipment["as_content"] == "<div>보존될 원문</div>"


# ---------------------------------------------------------------------------
# 2) legacy 영구화
# ---------------------------------------------------------------------------


def test_first_append_persists_legacy(client):
    """최초 append 가 기존 as_content 를 legacy 항목으로 흡수·보존한다."""
    _login_as_admin(client, username="as-contract-legacy")
    order = _create_as_order(
        shipment_extra={"as_content": "<div>옛 접수 원문</div>"}, as_content_2=None
    )
    order_id = order.id

    res = client.post(
        f"/api/orders/{order_id}/as/log", json={"type": "call", "text": "통화"}
    )
    assert res.status_code == 200

    db_session.expire_all()
    log = db_session.get(Order, order_id).structured_data["shipment"]["as_log"]
    assert any(
        e.get("legacy") is True and "옛 접수 원문" in e.get("text", "") for e in log
    )
    assert any(e.get("type") == "call" for e in log)


# ---------------------------------------------------------------------------
# 3) 퇴역 후에도 살아 있어야 하는 같은 라우트 경로
# ---------------------------------------------------------------------------


def test_sales_delivery_toggle_still_works(client):
    _login_as_admin(client, username="as-contract-sales")
    order = _create_as_order()
    order_id = order.id

    res = client.post(
        "/api/update_order_field",
        json={"order_id": order_id, "field_name": "sales_delivery", "new_value": True},
    )

    assert res.status_code == 200 and res.get_json()["success"] is True
    db_session.expire_all()
    saved = db_session.get(Order, order_id)
    assert saved.structured_data["shipment"]["sales_delivery"] is True


# ---------------------------------------------------------------------------
# 4) as_log 검색 (T10 U3)
# ---------------------------------------------------------------------------


def _log_entry(text: str, *, entry_id="al_1", log_type="memo") -> dict:
    return {
        "id": entry_id,
        "ts": "2026-07-24T00:00:00",
        "by": "관리자",
        "by_id": None,
        "type": log_type,
        "text": text,
        "edited_at": None,
        "edited_by": None,
    }


def test_search_finds_as_log_text(client):
    """quick-add 로 쌓인 as_log 본문이 검색에 잡힌다(as_content 에는 없는 문장)."""
    _login_as_admin(client, username="as-contract-search-1")
    _create_as_order(
        customer_name="로그검색대상",
        shipment_extra={"as_log": [_log_entry("<div>손잡이 교체 완료</div>")]},
    )
    _create_as_order(customer_name="검색제외대상")

    res = client.get("/erp/as?q=손잡이교체")

    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "로그검색대상" in body
    assert "검색제외대상" not in body


def test_search_survives_malformed_as_log(client):
    """as_log 가 배열이 아닌 오염 행 하나가 검색 전체를 500 으로 만들면 안 된다."""
    _login_as_admin(client, username="as-contract-search-3")
    _create_as_order(customer_name="오염행고객", shipment_extra={"as_log": "배열이 아님"})
    _create_as_order(
        customer_name="정상행고객",
        shipment_extra={"as_log": [_log_entry("<div>문틀 보수</div>")]},
    )

    res = client.get("/erp/as?q=문틀보수")

    assert res.status_code == 200
    assert "정상행고객" in res.get_data(as_text=True)


def test_search_still_finds_legacy_as_content(client):
    """legacy as_content 검색은 유지된다(as_log 확장이 기존 경로를 덮지 않는다)."""
    _login_as_admin(client, username="as-contract-search-2")
    _create_as_order(
        customer_name="레거시검색대상",
        shipment_extra={"as_content": "<div>경첩 파손</div>"},
        as_content_2=None,
    )
    _create_as_order(customer_name="레거시제외대상", as_content_2=None)

    res = client.get("/erp/as?q=경첩파손")

    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "레거시검색대상" in body
    assert "레거시제외대상" not in body
