"""주문 변경 이력 탭 계약 (ORDER-DIFF-02).

감사 화면(ADMIN 전용)과 달리 이 탭은 현장 직원도 여는 화면이다. 그래서 고정할 것이 둘 더 있다:
**가시성**(ADMIN 전체 / 그 외 본인 것만 — 기존 ``/change-events`` 규약)과
**지연 로딩**(주문 페이지 초기 페인트에 원장 조회를 얹지 않는다).
"""


from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderFieldChange, User


def _make_user(username: str, role: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team="CS",
        name=f"{username} 사용자",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _create_order() -> Order:
    order = Order(
        received_date="2026-08-11",
        customer_name="홍길동",
        phone="010-1234-5678",
        address="서울 테헤란로 123",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "RECEIVED"}, "items": [{"product_name": "붙박이장"}]},
    )
    db_session.add(order)
    db_session.commit()
    return order


def _seed_change(order_id: int, *, change_set: str, actor_id: int | None, path: str,
                 before: str | None, after: str | None, item_name: str | None = None) -> None:
    db_session.add(OrderFieldChange(
        change_set_id=change_set,
        order_id=order_id,
        path=path,
        path_template=path,
        item_index=None,
        item_name=item_name,
        op="set",
        before_value=before,
        after_value=after,
        actor_user_id=actor_id,
    ))
    db_session.commit()


def test_admin_sees_all_change_sets(client):
    """ADMIN 은 다른 사람이 바꾼 것까지 본다."""
    admin = _make_user("hist-admin", "ADMIN")
    staff = _make_user("hist-staff-a", "STAFF")
    order_id = _create_order().id
    _seed_change(order_id, change_set="cs-1", actor_id=staff.id,
                 path="schedule.measurement.date", before="2026-08-12", after="2026-08-14")
    _seed_change(order_id, change_set="cs-2", actor_id=admin.id,
                 path="workflow.stage", before="RECEIVED", after="MEASURE")
    _login(client, admin)

    payload = client.get(f"/api/orders/{order_id}/field-changes").get_json()

    assert payload["success"] is True
    sets = payload["data"]["change_sets"]
    assert {entry["change_set"] for entry in sets} == {"cs-1", "cs-2"}
    # 라벨·문장은 서버(표시 SSOT)가 붙인다 — 클라이언트가 사전을 갖지 않는다.
    texts = [change["text"] for entry in sets for change in entry["changes"]]
    assert any(text.startswith("실측일 ") for text in texts)
    assert all("RECEIVED" not in text for text in texts)  # 단계는 한글 단계명으로


def test_staff_sees_only_own_changes(client):
    """일반 사용자는 **본인이 바꾼 것만** 본다(기존 change-events 규약)."""
    mine = _make_user("hist-staff-b", "STAFF")
    other = _make_user("hist-staff-c", "STAFF")
    order_id = _create_order().id
    _seed_change(order_id, change_set="cs-mine", actor_id=mine.id,
                 path="parties.customer.phone", before="010-1111-2222", after="010-3333-4444")
    _seed_change(order_id, change_set="cs-other", actor_id=other.id,
                 path="totals.shipping_price", before="100000", after="200000")
    _login(client, mine)

    sets = client.get(f"/api/orders/{order_id}/field-changes").get_json()["data"]["change_sets"]

    assert [entry["change_set"] for entry in sets] == ["cs-mine"]


def test_changes_are_grouped_by_change_set_newest_first(client):
    """한 저장에서 바뀐 것들이 한 묶음으로, 최신 저장이 위로 온다."""
    admin = _make_user("hist-admin-2", "ADMIN")
    order_id = _create_order().id
    _seed_change(order_id, change_set="cs-old", actor_id=admin.id,
                 path="notes", before=None, after="이전 비고")
    _seed_change(order_id, change_set="cs-new", actor_id=admin.id,
                 path="schedule.construction.date", before=None, after="2026-09-01")
    _seed_change(order_id, change_set="cs-new", actor_id=admin.id,
                 path="items.0.price", before="100000", after="150000", item_name="붙박이장")
    _login(client, admin)

    sets = client.get(f"/api/orders/{order_id}/field-changes").get_json()["data"]["change_sets"]

    assert [entry["change_set"] for entry in sets] == ["cs-new", "cs-old"]
    assert len(sets[0]["changes"]) == 2
    assert sets[0]["actor"]["username"] == "hist-admin-2"
    assert sets[0]["changes"][1]["item"] == "붙박이장"


def test_missing_order_is_404(client):
    """없는 주문은 빈 목록이 아니라 404 다(빈 목록은 "이력이 없다"는 뜻이라 사실과 다르다)."""
    _login(client, _make_user("hist-admin-3", "ADMIN"))

    response = client.get("/api/orders/99999999/field-changes")

    assert response.status_code == 404
    assert response.get_json()["success"] is False


def test_tab_renders_empty_shell_without_data(client):
    """주문 페이지는 껍데기만 낸다 — 초기 페인트가 원장 조회를 기다리지 않는다."""
    admin = _make_user("hist-admin-4", "ADMIN")
    order_id = _create_order().id
    _seed_change(order_id, change_set="cs-x", actor_id=admin.id,
                 path="schedule.measurement.date", before="2026-08-12", after="2026-08-14")
    _login(client, admin)

    body = client.get(f"/edit/{order_id}").get_data(as_text=True)

    assert 'id="change-history-tab"' in body
    assert 'id="change-history"' in body
    assert "order-change-history.js" in body
    # 서버 렌더 HTML 에 원장 값이 실려 있으면 지연 로딩이 아니다.
    assert "2026-08-14" not in body
