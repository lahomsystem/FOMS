"""알림 수신자 resolver 서비스 (Phase 0A).

공유 `Notification` row 하나가 도달할 수신 사용자 목록을 per-source 로 산출하고,
`notification_user_states` row를 idempotent 하게 생성한다.

resolve 로직은 `foms.api.notifications._build_user_notification_filter`(사용자가 어떤
알림을 볼 수 있는지 판단하는 정방향 필터)의 **역방향**과 일치한다:
- target_user_id            -> 'target_user'
- target_type == 'ALL'      -> 활성 사용자 전체 'target_all'
- target_team (팀 일치)      -> 팀 활성 사용자 'target_team'
- target_manager_name 일치   -> 활성 사용자 'target_manager_name'

정방향 필터가 ADMIN 을 "전체 열람"으로 처리하는 것(read-path 관심사)은 여기서 상태를
물질화하지 않는다. 관리자에게 모든 알림 state 를 만드는 팬아웃은 의도가 아니며,
관리자는 위 4가지 경로(직접 지정/ALL/팀/이름)로만 state 를 가진다.
"""
from typing import Dict, Iterable, List, Tuple

from sqlalchemy import func

from models import NotificationRecipientSource, NotificationUserState, User

# 우선순위: 더 구체적인 경로가 낮은 우선순위를 덮어쓴다.
_SOURCE_ORDER = (
    NotificationRecipientSource.TARGET_ALL,
    NotificationRecipientSource.TARGET_TEAM,
    NotificationRecipientSource.TARGET_MANAGER_NAME,
    NotificationRecipientSource.TARGET_USER,
)


def resolve_recipients_for_notification(db, notification) -> List[Tuple[int, str]]:
    """Notification row -> dedupe 된 (user_id, recipient_source) 목록.

    inactive 사용자는 제외한다. 한 사용자가 여러 경로에 해당하면 가장 구체적인
    경로(target_user > target_manager_name > target_team > target_all)를 채택한다.

    :param db: SQLAlchemy 세션(scoped_session 또는 Session)
    :param notification: `models.Notification` 인스턴스
    :return: user_id 오름차순 정렬된 (user_id, recipient_source) 튜플 리스트
    """
    source_by_user: Dict[int, str] = {}

    ttype = (notification.target_type or '').strip().upper()
    if ttype == 'ALL':
        for (uid,) in db.query(User.id).filter(User.is_active == True).yield_per(500):  # noqa: E712
            source_by_user[int(uid)] = NotificationRecipientSource.TARGET_ALL

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
