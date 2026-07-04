"""Legacy Notification -> notification_user_states backfill 코어 로직 (Phase 0A).

CLI 래퍼는 `scripts/maintenance/backfill_notification_user_states.py`. 여기에는 단위
테스트가 가능한 순수 함수만 둔다. 두 번 실행해도 중복 state / 중복 ambiguous event 가
생기지 않도록 idempotent 하다.

legacy read 보존 규칙 (정확히):
- is_read=True 이고 read_by_user_id 있고 그 사용자가 수신자 -> 그 사용자 state 만
  read_at = Notification.read_at (다른 수신자는 unread).
- target_type=='USER' 이고 target_user_id==read_by_user_id -> 위 규칙에 포함(수신자이므로).
- is_read=True 이고 read_by_user_id 없음 -> read 확대 금지. `legacy_read_ambiguous`
  event 1건만 남기고 모든 state 는 unread.
"""
from typing import Callable, Dict, Optional, Tuple

from models import NotificationEvent, NotificationEventType, NotificationUserState
from foms.services.notifications.recipients import (
    ensure_user_states,
    resolve_recipients_for_notification,
)


def compute_read_and_ambiguous(
    notification, source_by_user: Dict[int, str]
) -> Tuple[Dict[int, object], bool]:
    """legacy read 보존 규칙을 적용해 (read_at_by_user, ambiguous) 를 계산.

    :param notification: `models.Notification`
    :param source_by_user: {user_id: recipient_source} — resolver 결과
    :return: (신규 state 에 적용할 {user_id: read_at}, ambiguous 여부)
    """
    read_at_by_user: Dict[int, object] = {}
    ambiguous = False
    if notification.is_read:
        reader = notification.read_by_user_id
        if reader is not None:
            if int(reader) in source_by_user:
                read_at_by_user[int(reader)] = notification.read_at or notification.created_at
            # reader 가 수신자가 아니면 read 확대 없이 무시(보수적).
        else:
            ambiguous = True
    return read_at_by_user, ambiguous


def has_ambiguous_event(db, notification_id: int) -> bool:
    """해당 notification 에 legacy_read_ambiguous event 가 이미 있는지 확인(중복 방지)."""
    row = (
        db.query(NotificationEvent.id)
        .filter(
            NotificationEvent.notification_id == notification_id,
            NotificationEvent.event_type == NotificationEventType.LEGACY_READ_AMBIGUOUS,
        )
        .first()
    )
    return row is not None


def process_notification(db, notification, dry_run: bool = False) -> Dict[str, int]:
    """Notification 1건을 backfill. state 생성 + audit event 를 idempotent 하게 기록.

    :param db: SQLAlchemy 세션
    :param notification: `models.Notification`
    :param dry_run: True 면 계산만 하고 DB 에 추가하지 않는다.
    :return: {'states_created': N, 'ambiguous_events': N} 카운트
    """
    recipients = resolve_recipients_for_notification(db, notification)
    source_by_user = {uid: src for uid, src in recipients}
    read_at_by_user, ambiguous = compute_read_and_ambiguous(notification, source_by_user)

    if dry_run:
        existing = {
            int(uid)
            for (uid,) in db.query(NotificationUserState.user_id).filter(
                NotificationUserState.notification_id == notification.id
            )
        }
        states_created = sum(1 for uid in source_by_user if int(uid) not in existing)
        ambiguous_events = 1 if (ambiguous and not has_ambiguous_event(db, notification.id)) else 0
        return {'states_created': states_created, 'ambiguous_events': ambiguous_events}

    created = ensure_user_states(db, notification, source_by_user, read_at_by_user)
    for state in created:
        db.add(
            NotificationEvent(
                notification_id=notification.id,
                user_state_id=state.id,
                recipient_user_id=state.user_id,
                event_type=NotificationEventType.STATE_BACKFILLED,
            )
        )

    ambiguous_events = 0
    if ambiguous and not has_ambiguous_event(db, notification.id):
        db.add(
            NotificationEvent(
                notification_id=notification.id,
                event_type=NotificationEventType.LEGACY_READ_AMBIGUOUS,
                metadata_json={
                    'is_read': True,
                    'read_by_user_id': None,
                    'read_at': notification.read_at.isoformat() if notification.read_at else None,
                },
            )
        )
        ambiguous_events = 1

    db.flush()
    return {'states_created': len(created), 'ambiguous_events': ambiguous_events}


def run_backfill(
    db,
    chunk_size: int = 500,
    dry_run: bool = False,
    start_id: int = 0,
    progress: Optional[Callable[[int, Dict[str, int]], None]] = None,
) -> Dict[str, int]:
    """notification_id 오름차순으로 chunk 단위 backfill 실행.

    각 chunk 처리 후 commit(dry-run 이면 rollback)하고 `progress(last_id, totals)` 를
    호출한다. resume 은 `start_id`(마지막 처리 id) 로 재개한다.

    :param db: SQLAlchemy 세션
    :param chunk_size: chunk 당 처리할 notification 수 및 commit 단위
    :param dry_run: True 면 커밋하지 않고 계산만.
    :param start_id: 이 id 초과부터 처리(resume cursor).
    :param progress: chunk 완료 시 (last_id, totals) 콜백
    :return: {'scanned', 'states_created', 'ambiguous_events', 'last_id'}
    """
    from models import Notification  # 지연 import (순환 방지)

    totals = {'scanned': 0, 'states_created': 0, 'ambiguous_events': 0, 'last_id': start_id}
    last_id = start_id
    while True:
        batch = (
            db.query(Notification)
            .filter(Notification.id > last_id)
            .order_by(Notification.id.asc())
            .limit(chunk_size)
            .all()
        )
        if not batch:
            break
        for notification in batch:
            result = process_notification(db, notification, dry_run=dry_run)
            totals['scanned'] += 1
            totals['states_created'] += result['states_created']
            totals['ambiguous_events'] += result['ambiguous_events']
            last_id = notification.id
        if dry_run:
            db.rollback()
        else:
            db.commit()
        totals['last_id'] = last_id
        if progress is not None:
            progress(last_id, dict(totals))
    return totals
