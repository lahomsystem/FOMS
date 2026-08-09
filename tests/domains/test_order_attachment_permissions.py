from __future__ import annotations

import io
from types import SimpleNamespace

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.attachment_visibility import include_deleted
from foms.services.order_attachment_permissions import (
    can_delete_order_attachment,
    can_manage_order_attachments,
    can_modify_order_attachment,
)
from models import Order, OrderAttachment, User


def _sales_order(*, manager_name: str = "영업담당", assignee_ids: list[int] | None = None) -> Order:
    assignments = {}
    if assignee_ids is not None:
        assignments["sales_assignee_user_ids"] = assignee_ids
    order = Order(
        received_date="2026-04-11",
        customer_name="고객",
        phone="010-1111-2222",
        address="서울",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        manager_name=manager_name,
        structured_data={
            "parties": {"manager": {"name": manager_name}},
            "assignments": assignments,
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


def _attachment(order: Order, *, user_id: int | None, uploader_id: int = 99) -> OrderAttachment:
    att = OrderAttachment(
        order_id=order.id,
        filename="photo.jpg",
        file_type="image",
        category="measurement",
        file_size=100,
        storage_key=f"orders/{order.id}/attachments/photo.jpg",
        user_id=user_id if user_id is not None else uploader_id,
    )
    db_session.add(att)
    db_session.commit()
    return att


def test_can_manage_order_attachments_for_admin_and_sales_assignee() -> None:
    admin = SimpleNamespace(id=1, role="ADMIN", name="관리자", username="admin", team="CS")
    sales_user = SimpleNamespace(id=42, role="STAFF", name="영업담당", username="sales1", team="SALES")
    outsider = SimpleNamespace(id=99, role="STAFF", name="다른사람", username="other", team="SALES")
    order = SimpleNamespace(
        manager_name="영업담당",
        structured_data={
            "parties": {"manager": {"name": "영업담당"}},
            "assignments": {"sales_assignee_user_ids": [42]},
        },
    )

    assert can_manage_order_attachments(admin, order)
    assert can_manage_order_attachments(sales_user, order)
    assert not can_manage_order_attachments(outsider, order)


def test_can_delete_order_attachment_manager_deletes_legacy_null_uploader() -> None:
    manager = SimpleNamespace(id=42, role="STAFF", name="영업담당", username="sales1", team="SALES")
    order = SimpleNamespace(
        manager_name="영업담당",
        structured_data={
            "parties": {"manager": {"name": "영업담당"}},
            "assignments": {},
        },
    )
    legacy_att = SimpleNamespace(user_id=None)

    assert can_delete_order_attachment(manager, order, legacy_att)


def test_can_delete_order_attachment_uploader_without_manager_role() -> None:
    uploader = SimpleNamespace(id=77, role="STAFF", name="실측팀", username="measure1", team="MEASURE")
    order = SimpleNamespace(
        manager_name="영업담당",
        structured_data={"parties": {"manager": {"name": "영업담당"}}, "assignments": {}},
    )
    own_att = SimpleNamespace(user_id=77)
    other_att = SimpleNamespace(user_id=88)

    assert can_delete_order_attachment(uploader, order, own_att)
    assert not can_delete_order_attachment(uploader, order, other_att)


def _login(client, user: User) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def test_attachment_delete_api_allows_order_manager_for_others_upload(client, monkeypatch) -> None:
    manager = User(
        username="attach-mgr",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="SALES",
        name="영업담당",
        is_active=True,
    )
    uploader = User(
        username="attach-uploader",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="MEASURE",
        name="실측팀",
        is_active=True,
    )
    db_session.add_all([manager, uploader])
    db_session.commit()

    order = _sales_order(manager_name="영업담당")
    attachment = _attachment(order, user_id=uploader.id)
    attachment_id = attachment.id

    class DummyStorage:
        def delete_file(self, key):
            return True

    monkeypatch.setattr("foms.api.files.order_routes.get_storage", lambda: DummyStorage())

    _login(client, manager)
    response = client.delete(f"/api/orders/{order.id}/attachments/{attachment_id}")

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    # ATTACH-LIFE-01: 삭제는 hard delete 가 아니라 tombstone 이다 — 조회에서 사라지되
    # row 는 남아 감사·복구가 가능하다(수명주기 계약은 test_attachment_lifecycle.py).
    assert db_session.query(OrderAttachment).filter_by(id=attachment_id).first() is None
    assert include_deleted(
        db_session.query(OrderAttachment).filter_by(id=attachment_id)
    ).one().deleted_at is not None


def test_attachment_delete_api_denies_unrelated_user(client) -> None:
    outsider = User(
        username="attach-outsider",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="SALES",
        name="다른영업",
        is_active=True,
    )
    uploader = User(
        username="attach-owner",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="MEASURE",
        name="실측팀",
        is_active=True,
    )
    db_session.add_all([outsider, uploader])
    db_session.commit()

    order = _sales_order(manager_name="영업담당")
    attachment = _attachment(order, user_id=uploader.id)

    _login(client, outsider)
    response = client.delete(f"/api/orders/{order.id}/attachments/{attachment.id}")

    assert response.status_code == 403
    assert "담당자" in response.get_json()["message"]


def test_attachment_list_includes_can_delete_for_manager(client) -> None:
    manager = User(
        username="attach-list-mgr",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="SALES",
        name="영업담당",
        is_active=True,
    )
    uploader = User(
        username="attach-list-uploader",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="MEASURE",
        name="실측팀",
        is_active=True,
    )
    db_session.add_all([manager, uploader])
    db_session.commit()

    order = _sales_order(manager_name="영업담당")
    _attachment(order, user_id=uploader.id)

    _login(client, manager)
    response = client.get(f"/api/orders/{order.id}/attachments")

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert len(data["attachments"]) == 1
    assert data["attachments"][0]["can_delete"] is True


def test_attachment_delete_api_allows_admin(client, monkeypatch) -> None:
    admin = User(
        username="attach-admin",
        password=generate_password_hash("pw"),
        role="ADMIN",
        team="CS",
        name="관리자",
        is_active=True,
    )
    uploader = User(
        username="attach-admin-uploader",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="SALES",
        name="영업담당",
        is_active=True,
    )
    db_session.add_all([admin, uploader])
    db_session.commit()

    order = _sales_order(manager_name="영업담당")
    attachment = _attachment(order, user_id=uploader.id)

    class DummyStorage:
        def delete_file(self, key):
            return True

    monkeypatch.setattr("foms.api.files.order_routes.get_storage", lambda: DummyStorage())

    _login(client, admin)
    response = client.delete(f"/api/orders/{order.id}/attachments/{attachment.id}")

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_can_manage_order_attachments_manager_numeric_id_token() -> None:
    manager = SimpleNamespace(id=42, role="STAFF", name="다른표기", username="sales42", team="SALES")
    order = SimpleNamespace(
        manager_name="42",
        structured_data={
            "parties": {"manager": {"name": "42"}},
            "assignments": {},
        },
    )
    assert can_manage_order_attachments(manager, order)


def test_can_manage_order_attachments_db_name_lookup(app) -> None:
    user = User(
        username="attach-db-lookup",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="SALES",
        name="DB매칭담당",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    order = _sales_order(manager_name="DB매칭담당", assignee_ids=None)
    order.structured_data = {
        "parties": {"manager": {"name": "DB매칭담당"}},
        "assignments": {},
    }
    db_session.commit()

    assert can_manage_order_attachments(user, order)


def test_can_manage_order_attachments_denies_drawing_assignee_only() -> None:
    drawing_user = SimpleNamespace(id=41, role="STAFF", name="도면담당", username="draw1", team="DRAWING")
    order = SimpleNamespace(
        manager_name="영업담당",
        structured_data={
            "parties": {"manager": {"name": "영업담당"}},
            "assignments": {"drawing_assignee_user_ids": [41]},
        },
    )
    assert not can_manage_order_attachments(drawing_user, order)


def test_can_modify_order_attachment_matches_delete_policy() -> None:
    manager = SimpleNamespace(id=42, role="STAFF", name="영업담당", username="sales1", team="SALES")
    outsider = SimpleNamespace(id=99, role="STAFF", name="다른사람", username="other", team="SALES")
    order = SimpleNamespace(
        manager_name="영업담당",
        structured_data={"parties": {"manager": {"name": "영업담당"}}, "assignments": {}},
    )
    att = SimpleNamespace(user_id=88)
    assert can_modify_order_attachment(manager, order, att)
    assert not can_modify_order_attachment(outsider, order, att)


def test_attachment_delete_api_assignee_ids_without_name_match(client, monkeypatch) -> None:
    manager = User(
        username="attach-assignee-id",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="SALES",
        name="표기불일치",
        is_active=True,
    )
    uploader = User(
        username="attach-assignee-uploader",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="MEASURE",
        name="실측팀",
        is_active=True,
    )
    db_session.add_all([manager, uploader])
    db_session.commit()

    order = _sales_order(manager_name="완전다른이름", assignee_ids=[manager.id])
    attachment = _attachment(order, user_id=uploader.id)

    class DummyStorage:
        def delete_file(self, key):
            return True

    monkeypatch.setattr("foms.api.files.order_routes.get_storage", lambda: DummyStorage())

    _login(client, manager)
    response = client.delete(f"/api/orders/{order.id}/attachments/{attachment.id}")

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_attachment_delete_api_uploader_self_delete(client, monkeypatch) -> None:
    uploader = User(
        username="attach-self-uploader",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="MEASURE",
        name="실측팀",
        is_active=True,
    )
    db_session.add(uploader)
    db_session.commit()

    order = _sales_order(manager_name="영업담당")
    attachment = _attachment(order, user_id=uploader.id)

    class DummyStorage:
        def delete_file(self, key):
            return True

    monkeypatch.setattr("foms.api.files.order_routes.get_storage", lambda: DummyStorage())

    _login(client, uploader)
    response = client.delete(f"/api/orders/{order.id}/attachments/{attachment.id}")

    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_attachment_list_can_delete_false_for_outsider(client) -> None:
    outsider = User(
        username="attach-list-outsider",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="SALES",
        name="다른영업",
        is_active=True,
    )
    uploader = User(
        username="attach-list-owner",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="MEASURE",
        name="실측팀",
        is_active=True,
    )
    db_session.add_all([outsider, uploader])
    db_session.commit()

    order = _sales_order(manager_name="영업담당")
    _attachment(order, user_id=uploader.id)

    _login(client, outsider)
    response = client.get(f"/api/orders/{order.id}/attachments")

    assert response.status_code == 200
    assert response.get_json()["attachments"][0]["can_delete"] is False


def test_attachment_delete_legacy_null_denied_to_outsider(client) -> None:
    outsider = User(
        username="attach-null-outsider",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="SALES",
        name="다른영업",
        is_active=True,
    )
    db_session.add(outsider)
    db_session.commit()

    order = _sales_order(manager_name="영업담당")
    attachment = OrderAttachment(
        order_id=order.id,
        filename="legacy.jpg",
        file_type="image",
        category="measurement",
        file_size=100,
        storage_key=f"orders/{order.id}/attachments/legacy.jpg",
        user_id=None,
    )
    db_session.add(attachment)
    db_session.commit()

    _login(client, outsider)
    response = client.delete(f"/api/orders/{order.id}/attachments/{attachment.id}")

    assert response.status_code == 403


def test_attachment_patch_denies_outsider(client) -> None:
    outsider = User(
        username="attach-patch-outsider",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="SALES",
        name="다른영업",
        is_active=True,
    )
    uploader = User(
        username="attach-patch-owner",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="MEASURE",
        name="실측팀",
        is_active=True,
    )
    db_session.add_all([outsider, uploader])
    db_session.commit()

    order = _sales_order(manager_name="영업담당")
    attachment = _attachment(order, user_id=uploader.id)

    _login(client, outsider)
    response = client.patch(
        f"/api/orders/{order.id}/attachments/{attachment.id}",
        json={"item_index": 0},
    )

    assert response.status_code == 403


def test_attachment_patch_allows_manager(client) -> None:
    manager = User(
        username="attach-patch-mgr",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="SALES",
        name="영업담당",
        is_active=True,
    )
    uploader = User(
        username="attach-patch-uploader",
        password=generate_password_hash("pw"),
        role="STAFF",
        team="MEASURE",
        name="실측팀",
        is_active=True,
    )
    db_session.add_all([manager, uploader])
    db_session.commit()

    order = _sales_order(manager_name="영업담당")
    attachment = _attachment(order, user_id=uploader.id)

    _login(client, manager)
    response = client.patch(
        f"/api/orders/{order.id}/attachments/{attachment.id}",
        json={"item_index": 0},
    )

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["attachment"]["item_index"] == 0
    assert data["attachment"]["can_delete"] is True
