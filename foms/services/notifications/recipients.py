"""알림 수신자 resolver 서비스 (Phase 0A).

공유 `Notification` row 하나가 도달할 수신 사용자 목록을 per-source 로 산출하고,
`notification_user_states` row를 idempotent 하게 생성한다.

resolve 로직은 `foms.api.notifications._build_user_notification_filter`(사용자가 어떤
알림을 볼 수 있는지 판단하는 정방향 필터)의 **역방향**과 일치한다:
- target_user_id            -> 'target_user'
- target_type == 'ALL'      -> 활성 사용자 전체 'target_all'
- target_role (역할 일치)     -> 해당 역할 활성 사용자 'target_role'
- target_team (팀 일치)      -> 팀 활성 사용자 'target_team'
- target_manager_name 일치   -> 활성 사용자 'target_manager_name'

정방향 필터가 ADMIN 을 "전체 열람"으로 처리하는 것(read-path 관심사)은 여기서 상태를
물질화하지 않는다. 관리자에게 모든 알림 state 를 만드는 팬아웃은 의도가 아니며,
관리자는 위 5가지 경로(직접 지정/ALL/역할/팀/이름)로만 state 를 가진다.
`target_role` 경로(NOTIF-ROLE-01)는 "관리자 전원에게" 같은 사건을 수신자 수만큼의
Notification row 로 복제하지 않기 위한 것으로, 알림을 만든 쪽이 역할을 **명시**했을
때만 동작한다(암묵적인 ADMIN 팬아웃이 아니다).
"""
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func

from models import (
    NotificationEvent,
    NotificationEventType,
    NotificationRecipientSource,
    NotificationUserState,
    User,
)

# 우선순위: 더 구체적인 경로가 낮은 우선순위를 덮어쓴다.
_SOURCE_ORDER = (
    NotificationRecipientSource.TARGET_ALL,
    NotificationRecipientSource.TARGET_ROLE,
    NotificationRecipientSource.TARGET_TEAM,
    NotificationRecipientSource.TARGET_MANAGER_NAME,
    NotificationRecipientSource.TARGET_USER,
)


def resolve_recipients_for_notification(db, notification) -> List[Tuple[int, str]]:
    """Notification row -> dedupe 된 (user_id, recipient_source) 목록.

    inactive 사용자는 제외한다. 한 사용자가 여러 경로에 해당하면 가장 구체적인
    경로(target_user > target_manager_name > target_team > target_role > target_all)를
    채택한다. 각 경로는 넓은 것부터 좁은 것 순으로 평가되어 뒤의 경로가 앞의 것을 덮어쓴다.

    :param db: SQLAlchemy 세션(scoped_session 또는 Session)
    :param notification: `models.Notification` 인스턴스
        (`target_role` 이 채워져 있으면 그 역할의 활성 사용자 전원이 수신자가 된다)
    :return: user_id 오름차순 정렬된 (user_id, recipient_source) 튜플 리스트
    """
    source_by_user: Dict[int, str] = {}

    ttype = (notification.target_type or '').strip().upper()
    if ttype == 'ALL':
        for (uid,) in db.query(User.id).filter(User.is_active == True).yield_per(500):  # noqa: E712
            source_by_user[int(uid)] = NotificationRecipientSource.TARGET_ALL

    role = (notification.target_role or '').strip().upper()
    if role:
        rows = db.query(User.id).filter(
            func.upper(User.role) == role, User.is_active == True  # noqa: E712
        ).yield_per(500)
        for (uid,) in rows:
            source_by_user[int(uid)] = NotificationRecipientSource.TARGET_ROLE

    team = (notification.target_team or '').strip().upper()
    if team:
        rows = db.query(User.id).filter(
            func.upper(User.team) == team, User.is_active == True  # noqa: E712
        ).yield_per(500)
        for (uid,) in rows:
            source_by_user[int(uid)] = NotificationRecipientSource.TARGET_TEAM

    manager = (notification.target_manager_name or '').strip()
    if manager:
        rows = db.query(User.id).filter(
            User.name == manager, User.is_active == True  # noqa: E712
        ).yield_per(500)
        for (uid,) in rows:
            source_by_user[int(uid)] = NotificationRecipientSource.TARGET_MANAGER_NAME

    if notification.target_user_id is not None:
        active = db.query(User.id).filter(
            User.id == notification.target_user_id, User.is_active == True  # noqa: E712
        ).first()
        if active is not None:
            source_by_user[int(notification.target_user_id)] = (
                NotificationRecipientSource.TARGET_USER
            )

    return sorted(source_by_user.items())


def ensure_user_states(
    db,
    notification,
    recipient_source_map: Iterable[Tuple[int, str]],
    read_at_by_user: Dict[int, object] = None,
) -> List[NotificationUserState]:
    """(notification_id, user_id) 충돌 시 no-op 인 idempotent state 생성 헬퍼.

    이미 존재하는 (notification, user) 조합은 건드리지 않고, 신규 조합만
    `NotificationUserState` 로 추가한다. 반환값은 이번 호출에서 신규 생성된 row 목록이며
    `db.flush()` 후이므로 각 row 의 id 가 채워져 있다.

    :param db: SQLAlchemy 세션
    :param notification: `models.Notification` 인스턴스
    :param recipient_source_map: (user_id, recipient_source) 반복자 또는 dict.items()
    :param read_at_by_user: {user_id: read_at datetime} — 신규 state 의 초기 read_at
    :return: 신규 생성된 NotificationUserState 리스트
    """
    read_at_by_user = read_at_by_user or {}
    existing = {
        int(uid)
        for (uid,) in db.query(NotificationUserState.user_id).filter(
            NotificationUserState.notification_id == notification.id
        )
    }
    created: List[NotificationUserState] = []
    for user_id, source in dict(recipient_source_map).items():
        uid = int(user_id)
        if uid in existing:
            continue
        state = NotificationUserState(
            notification_id=notification.id,
            user_id=uid,
            recipient_source=source,
            read_at=read_at_by_user.get(uid),
        )
        db.add(state)
        created.append(state)
        existing.add(uid)
    db.flush()
    return created


def fan_out_new_notification(
    db,
    notification,
    actor_user_id: Optional[int] = None,
) -> List[NotificationUserState]:
    """새 Notification 의 수신자 state 를 생성하고 'created' audit event 를 기록.

    반드시 `notification` 이 flush 되어 id 가 있는 상태에서 호출한다. state 생성과
    event 기록은 호출자의 트랜잭션에 그대로 참여한다(별도 commit 하지 않음). 알림 생성과
    같은 트랜잭션으로 묶여, state 없는 고아 알림 row 가 남지 않게 한다.

    :param db: SQLAlchemy 세션
    :param notification: id 가 채워진 `models.Notification` 인스턴스
    :param actor_user_id: 알림을 만든 사용자 id(감사용, 선택)
    :return: 이번 호출에서 신규 생성된 NotificationUserState 리스트
    """
    recipients = resolve_recipients_for_notification(db, notification)
    source_by_user = dict(recipients)
    created = ensure_user_states(db, notification, source_by_user)
    for state in created:
        db.add(
            NotificationEvent(
                notification_id=notification.id,
                user_state_id=state.id,
                actor_user_id=actor_user_id,
                recipient_user_id=state.user_id,
                event_type=NotificationEventType.CREATED,
            )
        )
    db.flush()
    return created
