"""사용자 삭제 FK 정리 PostgreSQL 계약 테스트 (PGTEST-00 lane).

deploy 에서 ``users.id`` 를 FK 로 잡는 테이블이 대거 추가됐고 그 FK 들에는 ``ON DELETE``
절이 없다. 실 PostgreSQL 에서만 FK 가 강제되므로(sqlite 도메인 레인은 미강제) 여기서
:func:`~foms.services.user_deletion.detach_user_references_for_delete` 가 실제로
``IntegrityError`` 를 막는지 검증한다.

``FOMS_TEST_DATABASE_URL`` 미설정이면 lane 자체가 skip 된다(conftest).
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from werkzeug.security import generate_password_hash

from foms.services.datetime_kst import now_utc_naive
from foms.services.user_deletion import (
    UserDeletionBlockedError,
    detach_user_references_for_delete,
)
from models import (
    AddressLearningRequest,
    FeatureCutoverMarker,
    InstallationWorker,
    Notification,
    NotificationEvent,
    NotificationPushSubscription,
    NotificationUserState,
    OpsApprovalRequest,
    Order,
    OrderAssignment,
    OrderInstallationAssignment,
    OrderMutationReceipt,
    SecurityPrincipalVersion,
    SystemSettingReceipt,
    UploadDraft,
    User,
)


def _create_user(session, username: str) -> User:
    """Insert an active STAFF user (users trigger seeds its principal version row)."""
    user = User(
        username=username,
        password=generate_password_hash("pw1234"),
        role="STAFF",
        name=username,
        is_active=True,
    )
    session.add(user)
    session.flush()
    return user


def _create_order(session) -> Order:
    """Insert a minimal RECEIVED order to hang order-scoped child rows on."""
    order = Order(
        received_date="2026-07-30",
        customer_name="FK 정리 테스트",
        phone="01077776666",
        address="서울시 테스트구 테스트로 3",
        product="붙박이장",
        status="RECEIVED",
    )
    session.add(order)
    session.flush()
    return order


def test_user_delete_survives_deploy_added_fk_tables(pg_session) -> None:
    """신규 FK 테이블에 행이 있어도 사용자 삭제가 IntegrityError 없이 끝나야 한다."""
    user = _create_user(pg_session, f"fkdel_{uuid.uuid4().hex[:8]}")
    order = _create_order(pg_session)
    now = now_utc_naive()

    notification = Notification(
        notification_type="ANNOUNCEMENT",
        target_type="USER",
        title="FK 정리 알림",
    )
    pg_session.add(notification)
    pg_session.flush()

    state = NotificationUserState(
        notification_id=notification.id,
        user_id=user.id,
        recipient_source="target_user",
    )
    worker = InstallationWorker(
        external_worker_id=f"EXT-{uuid.uuid4().hex[:8]}",
        display_name="설치 작업자",
        user_id=user.id,
    )
    pg_session.add_all([state, worker])
    pg_session.flush()

    pg_session.add_all(
        [
            NotificationEvent(
                notification_id=notification.id,
                user_state_id=state.id,
                actor_user_id=user.id,
                recipient_user_id=user.id,
                event_type="created",
            ),
            NotificationPushSubscription(
                user_id=user.id,
                endpoint=f"https://push.example/{uuid.uuid4().hex}",
            ),
            SystemSettingReceipt(
                actor_user_id=user.id,
                setting_key="shipment_reference",
                policy_id="POLICY-FKDEL",
                request_hash="a" * 64,
                response_status=200,
                response_body={},
                resulting_version=1,
                expires_at=now + timedelta(hours=24),
            ),
            OrderMutationReceipt(
                actor_user_id=user.id,
                policy_id="POLICY-FKDEL",
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
                nonce_hash=uuid.uuid4().hex + uuid.uuid4().hex,
                expires_at=now + timedelta(hours=1),
                approved_by_user_id=user.id,
                operator_identity_hash="f" * 64,
            ),
            AddressLearningRequest(
                original_address="서울시 오타구",
                corrected_address="서울시 정답구",
                requested_by_user_id=user.id,
            ),
            UploadDraft(
                order_id=order.id,
                kind="drawing_revision",
                created_by_user_id=user.id,
                expires_at=now + timedelta(hours=24),
            ),
            OrderInstallationAssignment(
                order_id=order.id,
                worker_id=worker.id,
                assigned_by_user_id=user.id,
                released_by_user_id=user.id,
            ),
        ]
    )
    pg_session.flush()

    # users INSERT trigger 가 principal version 행을 자동 seed 한다(PK FK).
    assert pg_session.query(SecurityPrincipalVersion).filter(
        SecurityPrincipalVersion.user_id == user.id
    ).count() == 1

    user_id = user.id
    detach_user_references_for_delete(pg_session, user_id)
    pg_session.delete(user)
    pg_session.flush()  # FK 위반이면 여기서 IntegrityError

    # detach 는 bulk UPDATE(synchronize_session=False)라 세션 안의 객체를 갱신하지 않는다.
    # expire 하지 않으면 아래 단언이 identity-map 의 낡은 값을 읽어 DB 실제 상태를 검증하지
    # 못한다(실측: installation_workers 행은 user_id=NULL 인데 객체는 옛 id 를 들고 있었다).
    pg_session.expire_all()

    assert pg_session.query(User).filter(User.id == user_id).count() == 0

    # 사람에게 종속된 행은 사라진다.
    assert pg_session.query(SecurityPrincipalVersion).filter(
        SecurityPrincipalVersion.user_id == user_id
    ).count() == 0
    assert pg_session.query(NotificationUserState).filter(
        NotificationUserState.user_id == user_id
    ).count() == 0
    assert pg_session.query(NotificationPushSubscription).count() == 0
    assert pg_session.query(SystemSettingReceipt).count() == 0
    assert pg_session.query(OrderMutationReceipt).count() == 0

    # 감사/설정 행은 남고 참조만 끊긴다.
    event = pg_session.query(NotificationEvent).one()
    assert (event.actor_user_id, event.recipient_user_id, event.user_state_id) == (None, None, None)
    assert pg_session.query(OpsApprovalRequest).one().approved_by_user_id is None
    assert pg_session.query(AddressLearningRequest).one().requested_by_user_id is None
    assert pg_session.query(UploadDraft).one().created_by_user_id is None
    assert pg_session.query(InstallationWorker).one().user_id is None

    installation = pg_session.query(OrderInstallationAssignment).one()
    assert (installation.assigned_by_user_id, installation.released_by_user_id) == (None, None)


def test_user_delete_refused_when_order_assignment_exists(pg_session) -> None:
    """권한 정본인 주문 배정이 남아 있으면 삭제를 거부한다(행 훼손 0)."""
    user = _create_user(pg_session, f"fkassign_{uuid.uuid4().hex[:8]}")
    order = _create_order(pg_session)
    pg_session.add(
        OrderAssignment(
            order_id=order.id,
            domain="SALES",
            user_id=user.id,
            source="SELF_CLAIM",
            assigned_by_user_id=user.id,
        )
    )
    pg_session.flush()

    with pytest.raises(UserDeletionBlockedError, match="주문 배정"):
        detach_user_references_for_delete(pg_session, user.id)

    assert pg_session.query(OrderAssignment).count() == 1


def test_user_delete_refused_when_feature_cutover_marker_exists(pg_session) -> None:
    """marker 는 DB trigger 가 UPDATE/DELETE 를 거부하므로 승인자도 삭제할 수 없다."""
    user = _create_user(pg_session, f"fkcutover_{uuid.uuid4().hex[:8]}")
    pg_session.add(
        FeatureCutoverMarker(
            family=f"test_family_{uuid.uuid4().hex[:6]}",
            cutover_sha="a" * 64,
            cutover_generation=1,
            minimum_compatibility_generation=1,
            readiness_artifact_sha256="b" * 64,
            ops_approval_id=str(uuid.uuid4()),
            approved_by_admin_user_id=user.id,
        )
    )
    pg_session.flush()

    with pytest.raises(UserDeletionBlockedError, match="cutover"):
        detach_user_references_for_delete(pg_session, user.id)

    assert pg_session.query(FeatureCutoverMarker).count() == 1
