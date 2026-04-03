from werkzeug.security import generate_password_hash

from db import db_session
from models import (
    ChannelManagerLink,
    ChatMessage,
    ChatRoom,
    ChatRoomMember,
    Notification,
    Order,
    OrderAttachment,
    OrderEstimate,
    User,
)


def _create_user(username: str, role: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw1234"),
        role=role,
        name=username,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login_as(client, user_id: int) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def test_delete_user_cleans_references_before_delete(client):
    admin = _create_user("admin_delete", "ADMIN")
    target = _create_user("target_delete", "STAFF")
    coworker = _create_user("coworker_delete", "STAFF")

    order = Order(
        received_date="2026-04-02",
        customer_name="삭제 테스트",
        phone="01012345678",
        address="서울시 테스트구 테스트로 1",
        product="붙박이장",
        status="RECEIVED",
    )
    db_session.add(order)
    db_session.commit()
    order_id = order.id

    room = ChatRoom(name="삭제 테스트 채팅방", created_by=target.id)
    db_session.add(room)
    db_session.commit()
    room_id = room.id

    db_session.add_all(
        [
            OrderAttachment(
                order_id=order.id,
                filename="proof.jpg",
                file_type="image",
                category="measurement",
                file_size=123,
                storage_key="orders/1/attachments/proof.jpg",
                thumbnail_key=None,
                user_id=target.id,
            ),
            Notification(
                notification_type="ANNOUNCEMENT",
                target_type="USER",
                title="삭제 테스트 알림",
                created_by_user_id=target.id,
                read_by_user_id=target.id,
                target_user_id=target.id,
            ),
            OrderEstimate(
                order_id=order.id,
                estimate_number="EST-DELETE-001",
                customer_name="삭제 테스트",
                estimate_date="2026-04-02",
                items=[],
                total_amount=0,
                status="DRAFT",
                created_by_user_id=target.id,
            ),
            ChannelManagerLink(
                channel_manager_id="channel-manager-delete",
                user_id=target.id,
                deactivated_by_user_id=target.id,
            ),
            ChatMessage(
                room_id=room.id,
                user_id=target.id,
                message_type="text",
                content="삭제 테스트 메시지",
            ),
            ChatMessage(
                room_id=room.id,
                user_id=coworker.id,
                message_type="text",
                content="동료 메시지",
            ),
            ChatRoomMember(
                room_id=room.id,
                user_id=target.id,
            ),
            ChatRoomMember(
                room_id=room.id,
                user_id=coworker.id,
            ),
        ]
    )
    db_session.commit()

    _login_as(client, admin.id)
    response = client.post(f"/admin/users/delete/{target.id}", follow_redirects=True)

    assert response.status_code == 200

    db_session.expire_all()

    assert db_session.query(User).filter(User.id == target.id).first() is None

    attachment = db_session.query(OrderAttachment).filter(OrderAttachment.order_id == order_id).one()
    assert attachment.user_id is None

    notification = db_session.query(Notification).one()
    assert notification.created_by_user_id is None
    assert notification.read_by_user_id is None
    assert notification.target_user_id is None

    estimate = db_session.query(OrderEstimate).one()
    assert estimate.created_by_user_id is None

    manager_link = db_session.query(ChannelManagerLink).one()
    assert manager_link.user_id is None
    assert manager_link.deactivated_by_user_id is None

    assert db_session.query(ChatRoom).filter(ChatRoom.id == room_id).count() == 0
    assert db_session.query(ChatMessage).count() == 0
    assert db_session.query(ChatRoomMember).count() == 0


def test_delete_user_requires_post(client):
    admin = _create_user("admin_method", "ADMIN")
    target = _create_user("target_method", "STAFF")

    _login_as(client, admin.id)
    response = client.get(f"/admin/users/delete/{target.id}", follow_redirects=False)

    assert response.status_code == 405
