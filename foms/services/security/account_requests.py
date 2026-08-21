"""ACCOUNT-SELF-01 — 셀프 가입 승인·비밀번호 재설정 요청 큐 서비스.

스펙: docs/specs/2026-08-06-account-self-service-design.md

* 셀프 가입은 ``users.approval_status`` 로 상태를 기록한다(ACTIVE|PENDING).
  거절은 상태 보존 없이 row 삭제(재신청 허용)이므로 REJECTED 값은 없다.
* 재설정 요청은 계정 열거 방지를 위해 username 실존 여부와 무관하게 접수하고
  (미매칭은 ``user_id`` NULL), 요청자에게 항상 동일한 성공 메시지를 보여준다.
* 관리자 알림은 사건 1건 = ROLE 타깃 Notification row 1건이며(NOTIF-ROLE-01),
  수신자별 state 는 ``fan_out_new_notification`` 훅이 만든다(알림 SSOT 규약).
  커밋은 호출자 몫.
"""
from __future__ import annotations

from typing import Optional

from foms.services.datetime_kst import now_utc_naive

#: users.approval_status 값 — 정상(로그인 허용).
APPROVAL_ACTIVE: str = 'ACTIVE'
#: users.approval_status 값 — 가입 신청 후 관리자 승인 대기(로그인 차단).
APPROVAL_PENDING: str = 'PENDING'

#: password_reset_requests.status 값.
RESET_PENDING: str = 'PENDING'
RESET_DONE: str = 'DONE'
RESET_DISMISSED: str = 'DISMISSED'

#: 알림 유형(Notification.notification_type).
NOTIF_ACCOUNT_SIGNUP: str = 'ACCOUNT_SIGNUP'
NOTIF_ACCOUNT_RESET_REQUEST: str = 'ACCOUNT_RESET_REQUEST'


def notify_admins_account_event(
    db,
    *,
    notification_type: str,
    title: str,
    message: str,
) -> int:
    """활성 ADMIN 전원에게 계정 이벤트 알림을 생성한다(커밋하지 않음).

    NOTIF-ROLE-01: 사건 1건 = ``target_type='ROLE'`` + ``target_role='ADMIN'`` 인 공유
    Notification row 1건이고, 수신자별 상태는 ``fan_out_new_notification`` 이 만드는
    ``notification_user_states`` 가 담당한다(관리자 수만큼 알림 row 를 복제하지 않는다).
    알림 생성과 state 생성이 호출자 트랜잭션에 함께 참여해 고아 알림이 남지 않는다.
    활성 ADMIN 이 0명이면 아무도 받지 못할 알림 row 를 만들지 않고 그대로 0 을 반환한다.

    :param db: SQLAlchemy 세션.
    :param notification_type: ``NOTIF_ACCOUNT_*`` 상수.
    :param title: 알림 제목(200자 이내).
    :param message: 알림 본문.
    :return: 생성된 수신자 state 수(활성 ADMIN 이 없으면 0).
    """
    from models import Notification, User
    from foms.services.notifications.recipients import fan_out_new_notification

    has_active_admin = (
        db.query(User.id)
        .filter(User.role == 'ADMIN', User.is_active.is_(True))
        .first()
    )
    if has_active_admin is None:
        return 0

    notif = Notification(
        notification_type=notification_type,
        target_type='ROLE',
        target_role='ADMIN',
        title=title,
        message=message,
    )
    db.add(notif)
    db.flush()
    return len(fan_out_new_notification(db, notif, actor_user_id=None))


def submit_password_reset_request(
    db,
    username_submitted: str,
    request_ip: Optional[str] = None,
):
    """비밀번호 재설정 요청을 접수한다(커밋하지 않음, 열거 방지 규약).

    username 매칭 여부와 무관하게 row 를 만들되, 매칭 사용자의 PENDING 요청이 이미
    있으면 중복 생성 없이 기존 row 를 반환한다(스팸 억제). 관리자 알림은 신규 접수
    시에만 생성한다.

    :param db: SQLAlchemy 세션.
    :param username_submitted: 폼에 입력된 username 원문(트림만 수행).
    :param request_ip: 감사용 요청 IP(선택).
    :return: ``(row, created)`` — 접수/기존 PasswordResetRequest 와 신규 여부.
    """
    from models import PasswordResetRequest, User

    username = (username_submitted or '').strip()[:64]
    matched = db.query(User).filter(User.username == username).first()

    if matched is not None:
        existing = (
            db.query(PasswordResetRequest)
            .filter(
                PasswordResetRequest.user_id == matched.id,
                PasswordResetRequest.status == RESET_PENDING,
            )
            .first()
        )
        if existing is not None:
            return existing, False

    row = PasswordResetRequest(
        username_submitted=username,
        user_id=matched.id if matched is not None else None,
        status=RESET_PENDING,
        created_at=now_utc_naive(),
        request_ip=request_ip,
    )
    db.add(row)
    db.flush()

    matched_note = (
        f"사용자 매칭: {matched.name}({matched.username})" if matched is not None
        else '일치하는 계정 없음(입력 원문만 기록)'
    )
    notify_admins_account_event(
        db,
        notification_type=NOTIF_ACCOUNT_RESET_REQUEST,
        title='비밀번호 재설정 요청',
        message=f"'{username}' 재설정 요청 접수 — {matched_note}. 사용자 관리에서 처리하세요.",
    )
    return row, True
