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

받는 사람 공통 규칙(FCOMM-01 겹 5 · 검수 원장 A4) — 이 파일의 :func:`broad_recipient_ids` ·
:func:`manager_name_recipient_ids` 두 함수가 정본이다. state 줄(종 · 폰 알림)을 만드는
:func:`resolve_recipients_for_notification` 과 실시간 소켓 전송 · 배지 무효화 대상을 고르는
``foms.api.notifications.resolve_notification_recipient_user_ids`` 가 둘 다 이 두 함수만 쓴다.

- 넓은 경로(전체 · 역할 · 팀)는 우리 직원만 받는다. 협력사 계정(:data:`INTERNAL_USERS_ONLY`)과
  켜진 프리랜서는 뺀다.
- 담당 이름 경로는 이름이 같은 직원이 받는다. 켜진 프리랜서는 이름만으로는 받지 않는다 — 그 주문에
  연결 줄(``order_freelancer_links``)이 있어야 받는다(J8). 주문을 모르면 프리랜서는 받지 않는다.
- 사람 지정(``target_user_id``) 경로는 그대로다(배정 알림 · 차감 알림이 이 길로 간다).

스펙: docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.3 겹 5
시험: tests/security/test_freelancer_notifications.py
"""
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from sqlalchemy import func

from foms.services.orders.order_mutation_policy import _TEAM_NORMALIZE, normalize_team
from foms.services.orders.manager_names import normalize_name_list
from foms.services.sales_commission.links import cached_snapshot
from foms.services.sales_commission.names import normalize_name
from models import (
    NotificationEvent,
    NotificationEventType,
    NotificationRecipientSource,
    NotificationUserState,
    OrderFreelancerLink,
    User,
)

# PARTNER-01: 넓은 경로(전체·role·팀·담당자 이름)는 우리 직원만 받는다. 외부 협력사 계정은
# target_user_id 로 직접 지정한 알림만 받는다(이름이 우연히 같아도 내부 알림이 새지 않게).
INTERNAL_USERS_ONLY = User.partner_org_id.is_(None)

# 우선순위: 더 구체적인 경로가 낮은 우선순위를 덮어쓴다.
_SOURCE_ORDER = (
    NotificationRecipientSource.TARGET_ALL,
    NotificationRecipientSource.TARGET_ROLE,
    NotificationRecipientSource.TARGET_TEAM,
    NotificationRecipientSource.TARGET_MANAGER_NAME,
    NotificationRecipientSource.TARGET_USER,
)


def expand_team_codes(team: str) -> Tuple[str, ...]:
    """팀 코드 하나를 "그 팀으로 정규화되는 모든 원본 표기"로 넓힌다.

    권한 판정은 legacy 표기 ``MEASURE`` 를 ``SALES`` 로 정규화한다
    (:data:`foms.services.orders.order_mutation_policy._TEAM_NORMALIZE`). 수신자 조회가
    ``User.team == 'SALES'`` 로만 찾으면 MEASURE 표기 영업 계정이 영업 대상 알림에서
    조용히 빠진다. 규칙 사본을 두지 않도록 정규화 표를 원천에서 그대로 읽는다.

    Args:
        team: 원본 팀 코드(대소문자·공백 무관).

    Returns:
        정규화된 팀 코드로 시작하는 tuple. 예: ``'SALES'`` → ``('SALES', 'MEASURE')``.
        빈 값이면 빈 tuple.
    """
    normalized = normalize_team(team)
    if not normalized:
        return ()
    aliases = tuple(
        sorted(raw for raw, target in _TEAM_NORMALIZE.items() if target == normalized and raw != normalized)
    )
    return (normalized,) + aliases


def team_condition(team: Any):
    """팀 경로 SQL 조건 — 그 팀으로 정규화되는 모든 표기(:func:`expand_team_codes`). 빈 팀이면 None."""
    codes = expand_team_codes(team or "")
    return func.upper(User.team).in_(codes) if codes else None


def active_freelancer_ids(db) -> frozenset:
    """켜진 프리랜서 id 묶음 — 요청 안이면 한 번만 읽는다(주문 저장 훅과 같은 캐시)."""
    return cached_snapshot(db).active_ids


def broad_recipient_ids(db, *conditions) -> Set[int]:
    """넓은 경로(전체 · 역할 · 팀 · 관리자 포함) 받는 사람 — 켜진 우리 직원 중 조건에 맞는 사람.

    협력사 계정과 켜진 프리랜서는 뺀다(FCOMM-01 겹 5). 조건을 여러 개 주면 모두 맞아야 한다.

    Args:
        db: SQLAlchemy 세션.
        *conditions: ``User`` 에 거는 SQL 조건(없으면 켜진 우리 직원 전체).

    Returns:
        user id 집합.
    """
    rows = db.query(User.id).filter(
        User.is_active == True, INTERNAL_USERS_ONLY, *conditions  # noqa: E712
    ).yield_per(500)
    ids = {int(uid) for (uid,) in rows}
    if not ids:
        return ids
    return ids - active_freelancer_ids(db)


def _int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def manager_name_recipient_ids(db, target_manager_name: Any, order_id: Any = None) -> Set[int]:
    """담당 이름 경로 받는 사람.

    이름이 같은 켜진 우리 직원(협력사 아님)이 받는다. 켜진 프리랜서는 이름(계정 이름 또는 설정의 맞출 이름)이
    대상 이름에 있고 **그 주문에 연결 줄이 있을 때만** 받는다 — 이름만 같으면 남의 주문 알림이 간다(J8).
    ``order_id`` 가 없으면 프리랜서는 받지 않는다.

    Args:
        db: SQLAlchemy 세션.
        target_manager_name: 담당 이름(여러 명이면 ``"김의종, 한용희"`` 처럼 이어 쓴 값 · 목록).
        order_id: 알림이 가리키는 주문 번호(없으면 None).

    Returns:
        user id 집합.
    """
    names = normalize_name_list(target_manager_name)
    if not names:
        return set()
    rows = db.query(User.id).filter(
        User.name.in_(names), User.is_active == True, INTERNAL_USERS_ONLY  # noqa: E712
    ).yield_per(500)
    by_name = {int(uid) for (uid,) in rows}
    snapshot = cached_snapshot(db)
    freelancers = snapshot.active_ids
    staff = by_name - freelancers
    oid = _int_or_none(order_id)
    if not freelancers or oid is None:
        return staff
    wanted = {normalize_name(n) for n in names}
    candidates = (by_name & freelancers) | {uid for name, uid in snapshot.match_map.items() if name in wanted}
    if not candidates:
        return staff
    linked = (
        db.query(OrderFreelancerLink.user_id)
        .join(User, User.id == OrderFreelancerLink.user_id)
        .filter(
            OrderFreelancerLink.order_id == oid,
            OrderFreelancerLink.user_id.in_(sorted(candidates)),
            User.is_active == True,  # noqa: E712
            INTERNAL_USERS_ONLY,
        )
        .distinct()
        .all()
    )
    return staff | {int(uid) for (uid,) in linked}


def resolve_recipients_for_notification(db, notification) -> List[Tuple[int, str]]:
    """Notification row -> dedupe 된 (user_id, recipient_source) 목록.

    inactive 사용자는 제외한다. 넓은 경로 · 담당 이름 경로는 공통 규칙(:func:`broad_recipient_ids` ·
    :func:`manager_name_recipient_ids`)을 따른다. 한 사용자가 여러 경로에 해당하면 가장 구체적인
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
        for uid in broad_recipient_ids(db):
            source_by_user[uid] = NotificationRecipientSource.TARGET_ALL

    role = (notification.target_role or '').strip().upper()
    if role:
        for uid in broad_recipient_ids(db, func.upper(User.role) == role):
            source_by_user[uid] = NotificationRecipientSource.TARGET_ROLE

    team_cond = team_condition(notification.target_team)
    if team_cond is not None:
        for uid in broad_recipient_ids(db, team_cond):
            source_by_user[uid] = NotificationRecipientSource.TARGET_TEAM

    # MULTI-MGR-01: 담당자 여러 명 알림은 "김의종, 한용희" 처럼 이어 넣는다. 프리랜서는 연결 줄이 있어야 받는다.
    for uid in manager_name_recipient_ids(db, notification.target_manager_name, notification.order_id):
        source_by_user[uid] = NotificationRecipientSource.TARGET_MANAGER_NAME

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
