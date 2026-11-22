"""도면 알림의 영업 쪽 받는 사람 규칙 — 도면 전달 · 전달 취소 · AS 도면 전달 · 도면 마감 알림이 같이 쓴다.

``foms/api/drawing/erp_orders_drawing.py`` 의 ``_drawing_notice_target`` 을 이름만 바꿔 옮겼다(설계서
``docs/specs/2026-11-22-production-drawing-arrival-upgrade_SPEC.md`` §9-3). 백그라운드 도면 마감 알림이 api 층을
거꾸로 부르지 않게 서비스 층에 둔다. 부르는 곳 넷은 ``tests/domains/test_drawing_notice_target_relocation.py`` 가 고정한다.
"""

from __future__ import annotations

from typing import Any, Optional, Set, Tuple

from sqlalchemy import func

from foms.services.notifications.recipients import (
    broad_recipient_ids,
    manager_name_recipient_ids,
    team_condition,
)
from foms.services.orders.manager_names import MANAGER_NAMES_SEPARATOR, normalize_name_list
from models import User

#: 담당자 이름에 이 글자가 들어간 주문(양산지사·양산)은 관리자가 직접 처리한다 — 담당자 경로에
#: 더해 관리자 역할 전원에게도 알림을 보낸다(2026-09-30 사용자 확정, 이시영).
ADMIN_HANDLED_MANAGER_KEYWORD = '양산'
#: 위 주문의 알림에 합집합으로 붙이는 역할(``Notification.target_role``).
ADMIN_HANDLED_TARGET_ROLE = 'ADMIN'

#: ``(target_team, target_manager_name, target_role)``
NoticeTarget = Tuple[Optional[str], Optional[str], Optional[str]]


def drawing_notice_target(db: Any, manager_name: Any, *, partner: bool = False) -> NoticeTarget:
    """도면 알림의 영업 쪽 수신 대상 ``(target_team, target_manager_name, target_role)``.

    외부 협력사 주문(``partner``) → CS 팀. 담당이 협력사 직원이라 알림을 받지 않으므로 우리 쪽은
    CS 가 챙긴다(스펙 §16 — 이름으로 찾으면 같은 이름의 우리 직원에게 가거나 영업팀 전체로 퍼진다).
    라홈·하우드 → CS 팀(TEAMS 의 CS = 라홈팀/하우드팀). 그 밖은 **담당 영업 본인만** 받는다 — 팀과 이름을
    함께 넣으면 수신자 resolver 가 합집합을 만들어 영업팀 전원에게 퍼진다. 담당자 이름이
    비었거나 활성 사용자와 맞지 않으면 알림이 사라지지 않도록 영업팀 전체로 되돌린다.

    담당자 이름에 :data:`ADMIN_HANDLED_MANAGER_KEYWORD`('양산')가 들어가면 관리자가 처리하는
    건이라 ``target_role='ADMIN'`` 을 함께 넣는다(담당 계정도 계속 받는 합집합). 이 경우엔
    관리자가 이미 받으므로 이름이 안 맞아도 영업팀 전체로 되돌리지 않는다.

    Args:
        db: 세션(이름 맞추기 쿼리 1개).
        manager_name: 주문 담당 표시 글(``order_manager_label`` — 여러 명이면 ``", "`` 로 이은 값).
        partner: 외부 협력사 주문이면 True.

    Returns:
        ``(target_team, target_manager_name, target_role)`` — 알림 줄 칸에 그대로 넣는다.
    """
    if partner:
        return 'CS', None, None
    name = (manager_name or '').strip()
    if '라홈' in name or '하우드' in name:
        return 'CS', None, None
    admin_handled = ADMIN_HANDLED_MANAGER_KEYWORD in name
    role = ADMIN_HANDLED_TARGET_ROLE if admin_handled else None
    # MULTI-MGR-01: 담당자 여러 명이면 활성 계정과 맞는 사람 모두가 받는다
    # (target_manager_name 에 ", " 로 이어 넣고, 수신자 resolver 가 나눠 읽는다).
    names = normalize_name_list(name)
    if names:
        matched = {
            str(row[0]) for row in db.query(User.name).filter(
                User.name.in_(names), User.is_active == True  # noqa: E712
            ).all()
        }
        matched_names = [n for n in names if n in matched]
        if matched_names:
            return None, MANAGER_NAMES_SEPARATOR.join(matched_names), role
    if admin_handled:
        return None, None, role
    return 'SALES', None, None


def notice_target_user_ids(db: Any, target: NoticeTarget, order_id: Any) -> Set[int]:
    """:func:`drawing_notice_target` 결과를 사람 id 로 — 알림 state 를 만드는 규칙과 같은 길로 센다.

    팀 · 역할 = 넓은 경로(켜진 우리 직원, 협력사 · 켜진 프리랜서 뺌), 이름 = 담당 이름 경로(켜진 프리랜서는 그 주문에
    연결 줄이 있을 때만). ``recipients.resolve_recipients_for_notification`` 과 같은 두 정본 함수만 쓴다.

    Args:
        db: 세션.
        target: ``(target_team, target_manager_name, target_role)``.
        order_id: 알림이 가리키는 주문 번호(프리랜서 연결 판정).

    Returns:
        user id 집합.
    """
    team, names, role = target
    out: Set[int] = set()
    team_cond = team_condition(team)
    if team_cond is not None:
        out |= broad_recipient_ids(db, team_cond)
    if role:
        out |= broad_recipient_ids(db, func.upper(User.role) == str(role).strip().upper())
    if names:
        out |= manager_name_recipient_ids(db, names, order_id)
    return out


__all__ = [
    "ADMIN_HANDLED_MANAGER_KEYWORD",
    "ADMIN_HANDLED_TARGET_ROLE",
    "NoticeTarget",
    "drawing_notice_target",
    "notice_target_user_ids",
]
