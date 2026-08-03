from datetime import timedelta

from werkzeug.security import generate_password_hash

from db import db_session
from models import (
    AddressLearningRequest,
    AuthRateKeyState,
    ChannelCreateFlag,
    ChannelInboundKeyState,
    ChannelManagerLink,
    ChatMessage,
    ChatRoom,
    ChatRoomMember,
    FeatureCutoverMarker,
    InstallationWorker,
    Notification,
    NotificationEvent,
    NotificationPushSubscription,
    NotificationUserState,
    OpsApprovalRequest,
    Order,
    OrderAssignment,
    OrderAttachment,
    OrderEstimate,
    OrderInstallationAssignment,
    OrderMutationReceipt,
    SecurityPrincipalVersion,
    SecuritySigningState,
    SystemSettingReceipt,
    UploadDraft,
    User,
    WDCLinkRuntimeState,
    now_utc_naive,
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

    notification = (
        db_session.query(Notification)
        .filter(Notification.title == "삭제 테스트 알림")
        .one()
    )
    assert notification.created_by_user_id is None
    assert notification.read_by_user_id is None
    assert notification.target_user_id is None

    estimate = (
        db_session.query(OrderEstimate)
        .filter(OrderEstimate.estimate_number == "EST-DELETE-001")
        .one()
    )
    assert estimate.created_by_user_id is None

    manager_link = (
        db_session.query(ChannelManagerLink)
        .filter(ChannelManagerLink.channel_manager_id == "channel-manager-delete")
        .one()
    )
    assert manager_link.user_id is None
    assert manager_link.deactivated_by_user_id is None

    assert db_session.query(ChatRoom).filter(ChatRoom.id == room_id).count() == 0
    assert db_session.query(ChatMessage).count() == 0
    assert db_session.query(ChatRoomMember).count() == 0


def _create_order(customer_name: str) -> Order:
    order = Order(
        received_date="2026-07-30",
        customer_name=customer_name,
        phone="01099998888",
        address="서울시 테스트구 테스트로 2",
        product="붙박이장",
        status="RECEIVED",
    )
    db_session.add(order)
    db_session.commit()
    return order


def test_delete_user_cleans_deploy_added_reference_tables(client):
    """deploy 에서 추가된 users.id FK 테이블도 삭제 전에 정리돼야 한다."""
    admin = _create_user("admin_newfk", "ADMIN")
    target = _create_user("target_newfk", "STAFF")
    order = _create_order("신규 FK 테스트")
    order_id = order.id
    now = now_utc_naive()

    notification = Notification(
        notification_type="ANNOUNCEMENT",
        target_type="USER",
        title="신규 FK 알림",
    )
    db_session.add(notification)
    db_session.commit()

    state = NotificationUserState(
        notification_id=notification.id,
        user_id=target.id,
        recipient_source="target_user",
    )
    worker = InstallationWorker(
        external_worker_id="EXT-DEL-1",
        display_name="설치 작업자",
        user_id=target.id,
    )
    db_session.add_all([state, worker])
    db_session.commit()

    db_session.add_all(
        [
            NotificationEvent(
                notification_id=notification.id,
                user_state_id=state.id,
                actor_user_id=target.id,
                recipient_user_id=target.id,
                event_type="created",
            ),
            NotificationPushSubscription(
                user_id=target.id,
                endpoint="https://push.example/endpoint-delete",
            ),
            SecurityPrincipalVersion(user_id=target.id, version=1),
            SystemSettingReceipt(
                actor_user_id=target.id,
                setting_key="shipment_reference",
                policy_id="POLICY-DEL",
                request_hash="a" * 64,
                response_status=200,
                response_body={},
                resulting_version=1,
                expires_at=now + timedelta(hours=24),
            ),
            OrderMutationReceipt(
                actor_user_id=target.id,
                policy_id="POLICY-DEL",
                scope_hash="b" * 64,
                request_hash="c" * 64,
                response_status=200,
                response_body={},
                resulting_versions={},
                read_expires_at=now + timedelta(minutes=2),
                expires_at=now + timedelta(hours=24),
            ),
            OpsApprovalRequest(
                operation_type="TEST_OP",
                scope_sha256="d" * 64,
                nonce_hash="e" * 64,
                expires_at=now + timedelta(hours=1),
                approved_by_user_id=target.id,
                operator_identity_hash="f" * 64,
            ),
            AddressLearningRequest(
                original_address="서울시 오타구",
                corrected_address="서울시 정답구",
                requested_by_user_id=target.id,
            ),
            UploadDraft(
                order_id=order.id,
                kind="drawing_revision",
                created_by_user_id=target.id,
                expires_at=now + timedelta(hours=24),
            ),
            WDCLinkRuntimeState(id=1, updated_by_admin_user_id=target.id),
            OrderInstallationAssignment(
                order_id=order.id,
                worker_id=worker.id,
                assigned_by_user_id=target.id,
                released_by_user_id=target.id,
            ),
        ]
    )
    # 싱글턴 설정 행은 create_all 이 이미 seed 했으므로 actor 만 채운다.
    for model in (SecuritySigningState, AuthRateKeyState, ChannelInboundKeyState, ChannelCreateFlag):
        row = db_session.query(model).filter(model.id == 1).one()
        row.updated_by_admin_user_id = target.id
    db_session.commit()

    _login_as(client, admin.id)
    response = client.post(f"/admin/users/delete/{target.id}", follow_redirects=True)

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(User).filter(User.id == target.id).first() is None

    # 사람에게 종속된 행은 사라진다.
    assert db_session.query(NotificationUserState).count() == 0
    assert db_session.query(NotificationPushSubscription).count() == 0
    assert db_session.query(SecurityPrincipalVersion).filter(
        SecurityPrincipalVersion.user_id == target.id
    ).count() == 0
    assert db_session.query(SystemSettingReceipt).count() == 0
    assert db_session.query(OrderMutationReceipt).count() == 0

    # 감사/설정 행은 남고 참조만 끊긴다.
    event = db_session.query(NotificationEvent).one()
    assert event.actor_user_id is None
    assert event.recipient_user_id is None
    assert event.user_state_id is None

    assert db_session.query(OpsApprovalRequest).one().approved_by_user_id is None
    assert db_session.query(AddressLearningRequest).one().requested_by_user_id is None
    assert db_session.query(UploadDraft).one().created_by_user_id is None
    assert db_session.query(WDCLinkRuntimeState).one().updated_by_admin_user_id is None
    assert db_session.query(InstallationWorker).one().user_id is None

    installation = db_session.query(OrderInstallationAssignment).one()
    assert installation.order_id == order_id
    assert installation.assigned_by_user_id is None
    assert installation.released_by_user_id is None

    for model in (SecuritySigningState, AuthRateKeyState, ChannelInboundKeyState, ChannelCreateFlag):
        assert db_session.query(model).filter(model.id == 1).one().updated_by_admin_user_id is None


def test_delete_user_refused_when_order_assignment_rows_remain(client):
    """주문 배정(권한 정본)이 남은 사용자는 삭제하지 않고 사유와 함께 거부한다."""
    admin = _create_user("admin_assign", "ADMIN")
    target = _create_user("target_assign", "STAFF")
    target_id = target.id
    order = _create_order("배정 차단 테스트")

    db_session.add(
        OrderAssignment(
            order_id=order.id,
            domain="SALES",
            user_id=target.id,
            source="SELF_CLAIM",
            assigned_by_user_id=target.id,
        )
    )
    db_session.commit()

    _login_as(client, admin.id)
    response = client.post(f"/admin/users/delete/{target_id}", follow_redirects=True)

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(User).filter(User.id == target_id).first() is not None
    assert db_session.query(OrderAssignment).count() == 1
    assert "주문 배정" in response.get_data(as_text=True)


def test_delete_user_refused_when_feature_cutover_marker_remains(client):
    """DB trigger 가 UPDATE/DELETE 를 막는 cutover marker 승인자는 삭제할 수 없다."""
    admin = _create_user("admin_cutover", "ADMIN")
    target = _create_user("target_cutover", "STAFF")
    target_id = target.id

    db_session.add(
        FeatureCutoverMarker(
            family="order_assignment",
            cutover_sha="a" * 64,
            cutover_generation=1,
            minimum_compatibility_generation=1,
            readiness_artifact_sha256="b" * 64,
            ops_approval_id="00000000-0000-0000-0000-000000000001",
            approved_by_admin_user_id=target.id,
        )
    )
    db_session.commit()

    _login_as(client, admin.id)
    response = client.post(f"/admin/users/delete/{target_id}", follow_redirects=True)

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(User).filter(User.id == target_id).first() is not None
    assert db_session.query(FeatureCutoverMarker).count() == 1
    assert "되돌릴 수 없는 시스템 설정" in response.get_data(as_text=True)


def test_delete_user_requires_post(client):
    admin = _create_user("admin_method", "ADMIN")
    target = _create_user("target_method", "STAFF")

    _login_as(client, admin.id)
    response = client.get(f"/admin/users/delete/{target.id}", follow_redirects=False)

    assert response.status_code == 405
