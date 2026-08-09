"""관리자 "사용자 삭제" 라우트 계약 — AUDIT-LOG T11 개정판.

**계약 개정 사유(T11 / 스펙 §8 결정 ⑤)**: 이 스위트는 원래 "관리자 삭제 = ``users`` row
hard delete + 모든 참조 NULL" 을 단언했다. 그 설계는 ``security_logs``·``order_events``·
``access_logs``·``order_attachments`` 의 actor 를 일괄 NULL 로 밀어서, 사용자를 지우는
순간 "누가 했는가"가 감사 원장에서 사후 소멸했다. 그래서 hard delete 단언을
**비활성화(탈퇴 처리) 단언**으로 개정한다:

* ``users`` row 는 남고 ``is_active=False`` + username 익명화 + 로그인 차단,
* 감사 actor 4종은 **그대로 보존**,
* 운영 참조(담당·수신·견적·채널 링크)는 종전대로 NULL,
* Chat 3종은 종전대로 hard delete.

hard delete 자체는 가입 신청 거절(``reject_user``) 경로에만 남아 있다. 그래서 삭제
차단(``UserDeletionBlockedError``) 계약도 이 파일에서는 거절 라우트로 검증한다.
"""

from datetime import timedelta

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.security.account_requests import APPROVAL_PENDING
from models import (
    AccessLog,
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
    OrderEvent,
    OrderInstallationAssignment,
    OrderMutationReceipt,
    SecurityLog,
    SecurityPrincipalVersion,
    SecuritySigningState,
    SystemSettingReceipt,
    UploadDraft,
    User,
    WDCLinkRuntimeState,
    now_utc_naive,
)

_TARGET_PASSWORD = "pw1234abc"


def _create_user(username: str, role: str, approval_status: str = "ACTIVE") -> User:
    user = User(
        username=username,
        password=generate_password_hash(_TARGET_PASSWORD),
        role=role,
        name=username,
        is_active=True,
        approval_status=approval_status,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login_as(client, user_id: int) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id


def _seed_order() -> Order:
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
    return order


def _seed_references(order: Order, target: User, coworker: User) -> ChatRoom:
    """감사 actor 4종 + 운영 참조 + Chat 3종을 target 사용자에 물려 둔다."""
    room = ChatRoom(name="삭제 테스트 채팅방", created_by=target.id)
    db_session.add(room)
    db_session.commit()

    db_session.add_all(
        [
            SecurityLog(user_id=target.id, message="감사 보존 대상 행"),
            AccessLog(user_id=target.id, action="FILE_VIEW"),
            OrderEvent(
                order_id=order.id,
                event_type="STAGE_CHANGED",
                created_by_user_id=target.id,
            ),
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
            ChatRoomMember(room_id=room.id, user_id=target.id),
            ChatRoomMember(room_id=room.id, user_id=coworker.id),
        ]
    )
    db_session.commit()
    return room


def test_delete_user_deactivates_and_preserves_audit_actor(client):
    """삭제 = 비활성화 전환 — 감사 actor 는 남고 운영 참조만 끊긴다(T11)."""
    admin = _create_user("admin_delete", "ADMIN")
    target = _create_user("target_delete", "STAFF")
    coworker = _create_user("coworker_delete", "STAFF")

    order = _seed_order()
    order_id = order.id
    room = _seed_references(order, target, coworker)
    room_id = room.id
    target_id = target.id

    _login_as(client, admin.id)
    response = client.post(f"/admin/users/delete/{target_id}", follow_redirects=True)

    assert response.status_code == 200

    db_session.expire_all()

    # 1) row 는 남되 비활성·익명화된다 (감사 FK 가 유효해야 하므로 row 를 지우지 않는다).
    deactivated = db_session.query(User).filter(User.id == target_id).one()
    assert deactivated.is_active is False
    assert deactivated.username == f"deleted_{target_id}_target_delete"
    assert deactivated.name == "탈퇴 사용자"

    # 2) 감사 actor 4종 보존 — "누가 했는가"가 소멸하지 않는다.
    audit_log = db_session.query(SecurityLog).filter(SecurityLog.message == "감사 보존 대상 행").one()
    assert audit_log.user_id == target_id

    access_log = db_session.query(AccessLog).filter(AccessLog.action == "FILE_VIEW").one()
    assert access_log.user_id == target_id

    event = db_session.query(OrderEvent).filter(OrderEvent.order_id == order_id).one()
    assert event.created_by_user_id == target_id

    attachment = db_session.query(OrderAttachment).filter(OrderAttachment.order_id == order_id).one()
    assert attachment.user_id == target_id

    # 3) 운영 참조는 종전대로 끊긴다.
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

    # 4) Chat 3종은 여전히 hard delete.
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
    """deploy 에서 추가된 users.id FK 테이블도 비활성화 시 정리돼야 한다.

    T11 이후 이 라우트는 row 를 지우지 않으므로 "사용자 행이 사라졌다" 단언은
    "비활성화됐다"로 바뀐다. 참조 정리 계약(운영 참조 NULL / 개인 종속 행 삭제)은
    deploy 신규 테이블에도 그대로 적용된다.
    """
    admin = _create_user("admin_newfk", "ADMIN")
    target = _create_user("target_newfk", "STAFF")
    target_id = target.id
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
    state_id = state.id

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
    response = client.post(f"/admin/users/delete/{target_id}", follow_redirects=True)

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(User).filter(User.id == target_id).one().is_active is False

    # 사람에게 종속된 행은 사라진다.
    assert db_session.query(NotificationPushSubscription).count() == 0
    assert db_session.query(SecurityPrincipalVersion).filter(
        SecurityPrincipalVersion.user_id == target_id
    ).count() == 0
    assert db_session.query(SystemSettingReceipt).count() == 0
    assert db_session.query(OrderMutationReceipt).count() == 0

    # 감사/설정 행은 남고 참조만 끊긴다.
    event = db_session.query(NotificationEvent).one()
    assert event.actor_user_id is None
    assert event.recipient_user_id is None
    # 개인 알림 상태 행은 users row 가 살아 있으므로 그대로 두고, append-only 감사 로그의
    # 링크도 끊지 않는다(hard delete 경로에서만 상태 행 삭제 + 링크 NULL).
    assert db_session.query(NotificationUserState).count() == 1
    assert event.user_state_id == state_id

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


def test_delete_user_proceeds_despite_blocking_audit_references(client):
    """비활성화 경로는 차단 참조가 있어도 막히지 않는다 — row 가 남아 FK 가 유효하다.

    hard delete 시절 거부 사유였던 주문 배정·cutover marker 는 비활성화에서는 아무것도
    막지 않는다(거부 메시지가 안내하던 대안이 바로 이 경로다). 배정 정본은 그대로 남는다.
    """
    admin = _create_user("admin_blockfree", "ADMIN")
    target = _create_user("target_blockfree", "STAFF")
    target_id = target.id
    order = _create_order("배정 보존 테스트")

    db_session.add_all(
        [
            OrderAssignment(
                order_id=order.id,
                domain="SALES",
                user_id=target.id,
                source="SELF_CLAIM",
                assigned_by_user_id=target.id,
            ),
            FeatureCutoverMarker(
                family="order_assignment",
                cutover_sha="a" * 64,
                cutover_generation=1,
                minimum_compatibility_generation=1,
                readiness_artifact_sha256="b" * 64,
                ops_approval_id="00000000-0000-0000-0000-000000000001",
                approved_by_admin_user_id=target.id,
            ),
        ]
    )
    db_session.commit()

    _login_as(client, admin.id)
    response = client.post(f"/admin/users/delete/{target_id}", follow_redirects=True)

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(User).filter(User.id == target_id).one().is_active is False
    assignment = db_session.query(OrderAssignment).one()
    assert assignment.user_id == target_id
    assert assignment.assigned_by_user_id == target_id
    assert db_session.query(FeatureCutoverMarker).one().approved_by_admin_user_id == target_id


def test_reject_user_refused_when_order_assignment_rows_remain(client):
    """hard delete(가입 거절)는 주문 배정이 남으면 사유와 함께 거부한다."""
    admin = _create_user("admin_assign", "ADMIN")
    target = _create_user("target_assign", "STAFF", approval_status=APPROVAL_PENDING)
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
    response = client.post(f"/admin/users/reject/{target_id}", follow_redirects=True)

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(User).filter(User.id == target_id).first() is not None
    assert db_session.query(OrderAssignment).count() == 1
    assert "주문 배정" in response.get_data(as_text=True)


def test_reject_user_refused_when_feature_cutover_marker_remains(client):
    """DB trigger 가 UPDATE/DELETE 를 막는 cutover marker 승인자는 지울 수 없다."""
    admin = _create_user("admin_cutover", "ADMIN")
    target = _create_user("target_cutover", "STAFF", approval_status=APPROVAL_PENDING)
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
    response = client.post(f"/admin/users/reject/{target_id}", follow_redirects=True)

    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.query(User).filter(User.id == target_id).first() is not None
    assert db_session.query(FeatureCutoverMarker).count() == 1
    assert "되돌릴 수 없는 시스템 설정" in response.get_data(as_text=True)


def test_delete_user_records_structured_deactivation_audit(client):
    """비활성화는 ``USER_DEACTIVATE`` + 원본 username 을 구조화 기록한다(T8 인자)."""
    admin = _create_user("admin_audit", "ADMIN")
    target = _create_user("target_audit", "STAFF")
    admin_id = admin.id
    target_id = target.id

    _login_as(client, admin_id)
    client.post(f"/admin/users/delete/{target_id}", follow_redirects=True)

    db_session.expire_all()
    row = (
        db_session.query(SecurityLog)
        .filter(SecurityLog.action == "USER_DEACTIVATE")
        .one()
    )
    assert row.user_id == admin_id
    assert row.target_type == "user"
    assert row.target_id == target_id
    assert row.detail["username_before"] == "target_audit"
    assert row.detail["username_after"] == f"deleted_{target_id}_target_audit"
    assert row.detail["was_active"] is True


def test_delete_user_blocks_login_and_frees_username(client):
    """비활성화 후 원본 아이디는 재사용 가능하고, 옛 비밀번호로는 로그인할 수 없다."""
    admin = _create_user("admin_login", "ADMIN")
    target = _create_user("target_login", "STAFF")
    target_id = target.id

    _login_as(client, admin.id)
    client.post(f"/admin/users/delete/{target_id}", follow_redirects=True)
    db_session.expire_all()

    # 익명화된 아이디 + 옛 비밀번호로는 로그인 불가(비활성 계정 차단).
    with client.session_transaction() as sess:
        sess.clear()
    blocked = client.post(
        "/login",
        data={"username": f"deleted_{target_id}_target_login", "password": _TARGET_PASSWORD},
        follow_redirects=True,
    )
    assert "비활성화된 계정입니다" in blocked.get_data(as_text=True)
    with client.session_transaction() as sess:
        assert "user_id" not in sess

    # 원본 아이디는 비었으므로 같은 아이디로 새 계정을 만들 수 있다(unique 충돌 없음).
    revived = _create_user("target_login", "STAFF")
    assert revived.id != target_id
    assert db_session.query(User).filter(User.username == "target_login").count() == 1


def test_delete_user_requires_post(client):
    admin = _create_user("admin_method", "ADMIN")
    target = _create_user("target_method", "STAFF")

    _login_as(client, admin.id)
    response = client.get(f"/admin/users/delete/{target.id}", follow_redirects=False)

    assert response.status_code == 405
