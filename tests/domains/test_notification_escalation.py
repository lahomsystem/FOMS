"""에스컬레이션 알림 본문/중복 억제 계약 테스트.

회귀 배경(2026-08-20): 원본 긴급 알림 5건이 4명에게 팬아웃된 상태에서 스윕이 돌자
ADMIN 1인에게 같은 제목의 빈 알림 20건이 쌓였다(원본당 1건이 아니라 state 당 1건).
게다가 ``message=None`` 이라 목록에 제목만 보여 무슨 일인지 알 수 없었다.

계약:
1. 에스컬레이션 알림 message 에 원본 제목·담당자·경과·원본 요약이 들어간다.
2. 같은 원본으로 같은 상급자에게는 스윕/단계를 넘어 1건만 생성된다.
3. push payload 는 여전히 generic (message 를 읽지 않는다).
"""
import datetime

import pytest

from db import db_session
from models import (
    Notification,
    NotificationDeliveryStatus,
    NotificationEventType,
    NotificationRecipientSource,
    NotificationUserState,
    User,
)
from foms.services.notifications.escalation import escalate_overdue_urgent
from foms.services.notifications.push_sender import _build_payload

NOW = datetime.datetime(2026, 8, 20, 9, 23, 0)


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


def _mk_user(username, name, role="VIEWER", team=None):
    user = User(
        username=username, password="x", name=name, role=role, team=team, is_active=True
    )
    db_session.add(user)
    db_session.flush()
    return user


def _mk_urgent(title, message, **kwargs):
    notif = Notification(
        notification_type="NAVER_RETURN_REQUESTED",
        target_type="USER",
        title=title,
        message=message,
        is_urgent=True,
        **kwargs,
    )
    db_session.add(notif)
    db_session.flush()
    return notif


def _mk_state(notif, user, created_at=None, escalated_at=None):
    state = NotificationUserState(
        notification_id=notif.id,
        user_id=user.id,
        recipient_source=NotificationRecipientSource.TARGET_USER,
        last_delivery_status=NotificationDeliveryStatus.PENDING,
        escalated_at=escalated_at,
    )
    db_session.add(state)
    db_session.flush()
    if created_at is not None:
        state.created_at = created_at
        db_session.flush()
    return state


def _escalations(user_id):
    return (
        db_session.query(Notification)
        .filter_by(notification_type="URGENT_ESCALATION", target_user_id=user_id)
        .all()
    )


def test_escalation_message_carries_source_context(db):
    """본문에 담당자·경과·원본 제목·원본 요약·주문번호가 담긴다."""
    victim = _mk_user("esc_msg_victim", "김담당", team="CS")
    manager = _mk_user("esc_msg_mgr", "박매니저", role="MANAGER", team="CS")
    notif = _mk_urgent(
        "네이버 반품 요청",
        "네이버에서 반품 요청 상태로 바뀐 주문이 있습니다. (상품주문번호 2026081442413251)",
        target_user_id=victim.id,
    )
    _mk_state(notif, victim, created_at=NOW - datetime.timedelta(minutes=6))

    escalate_overdue_urgent(db, now=NOW)

    rows = _escalations(manager.id)
    assert len(rows) == 1
    message = rows[0].message or ""
    assert "김담당(CS)" in message
    assert "5분" in message
    assert "네이버 반품 요청" in message
    assert "2026081442413251" in message


def test_escalation_message_truncates_long_source_body(db):
    """원본 본문이 길어도 한 줄 요약으로 잘린다(목록 가독성)."""
    victim = _mk_user("esc_long_victim", "김담당", team="CS")
    manager = _mk_user("esc_long_mgr", "박매니저", role="MANAGER", team="CS")
    notif = _mk_urgent("긴 알림", "가" * 500, target_user_id=victim.id)
    _mk_state(notif, victim, created_at=NOW - datetime.timedelta(minutes=6))

    escalate_overdue_urgent(db, now=NOW)

    message = (_escalations(manager.id)[0].message) or ""
    assert "…" in message
    assert "가" * 200 not in message


def test_one_escalation_per_source_even_with_many_states(db):
    """원본 1건이 4명에게 팬아웃돼도 매니저는 1건만 받는다."""
    manager = _mk_user("esc_dedup_mgr", "박매니저", role="MANAGER", team="CS")
    notif = _mk_urgent("네이버 반품 요청", "본문")
    for idx in range(4):
        victim = _mk_user(f"esc_dedup_v{idx}", f"담당{idx}", team="CS")
        _mk_state(notif, victim, created_at=NOW - datetime.timedelta(minutes=6))

    result = escalate_overdue_urgent(db, now=NOW)

    assert result["escalated"] == 4  # state 4건 모두 escalate 처리
    assert len(_escalations(manager.id)) == 1  # 알림은 원본당 1건
    assert result["recipient_user_ids"] == [manager.id]


def test_stage2_skips_users_already_escalated_for_same_source(db):
    """stage1 에서 ADMIN 폴백으로 이미 받은 사람은 stage2 에서 또 받지 않는다."""
    admin = _mk_user("esc_stage2_admin", "관리자", role="ADMIN")
    victim = _mk_user("esc_stage2_victim", "김담당", team="CS")  # 팀 매니저 없음
    notif = _mk_urgent("네이버 반품 요청", "본문", target_user_id=victim.id)
    state = _mk_state(notif, victim, created_at=NOW - datetime.timedelta(minutes=6))

    escalate_overdue_urgent(db, now=NOW)
    assert len(_escalations(admin.id)) == 1  # stage1 폴백

    later = NOW + datetime.timedelta(minutes=6)
    result2 = escalate_overdue_urgent(db, now=later)

    assert result2["operator_escalated"] == 1  # stage2 는 진행(이벤트 기록)
    assert len(_escalations(admin.id)) == 1  # 같은 사람에게 중복 발송은 없음
    db.refresh(state)
    assert state.ack_at is None


def test_escalation_push_payload_stays_generic(db):
    """본문이 생겨도 push payload 에는 고객/주문 정보가 실리지 않는다."""
    victim = _mk_user("esc_push_victim", "김담당", team="CS")
    manager = _mk_user("esc_push_mgr", "박매니저", role="MANAGER", team="CS")
    notif = _mk_urgent(
        "고객 홍길동 #123 주문", "현장 주소 서울시 강남구", target_user_id=victim.id
    )
    _mk_state(notif, victim, created_at=NOW - datetime.timedelta(minutes=6))

    escalate_overdue_urgent(db, now=NOW)
    payload = _build_payload(_escalations(manager.id)[0])

    blob = str(payload)
    assert "홍길동" not in blob
    assert "강남구" not in blob
    assert payload["title"] == "에스컬레이션"
