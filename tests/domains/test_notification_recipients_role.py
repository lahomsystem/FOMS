"""NOTIF-ROLE-01: `target_role` 수신자 경로 계약 테스트.

배경: "관리자 전원에게" 가는 알림이 수신자 수만큼 별개 Notification row 로 복제돼
왔다. 알림 SSOT 는 공유 Notification 1건 + 수신자별 `notification_user_states` 이므로,
`target_type='ROLE'` + `target_role='ADMIN'` 경로로 사건 1건 = row 1건을 회복한다.

계약:
1. 활성 ADMIN 전원이 `target_role` source 로 수신자가 된다(비활성은 제외).
2. 더 좁은 경로(target_user)가 역할 경로를 덮어쓴다.
3. 팬아웃은 idempotent — 재호출해도 state/event 가 늘지 않는다.
4. `target_role` 이 NULL 인 기존 알림의 동작은 바뀌지 않는다.

DB fixture 는 tests/conftest.py 의 `app` 픽스처(in-memory sqlite + create_all)를 쓴다.
"""
import pytest

from db import db_session
from models import (
    Notification,
    NotificationEvent,
    NotificationEventType,
    NotificationRecipientSource,
    NotificationUserState,
    User,
)
from foms.services.notifications.recipients import (
    fan_out_new_notification,
    resolve_recipients_for_notification,
)


@pytest.fixture
def db(app):
    """conftest `app` 픽스처로 스키마를 만들고 세션을 정리한다."""
    yield db_session
    db_session.rollback()


def _mk_user(username, name, role="VIEWER", team=None, is_active=True):
    user = User(
        username=username,
        password="x",
        name=name,
        team=team,
        role=role,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _mk_notification(**kwargs):
    defaults = dict(
        notification_type="ANNOUNCEMENT",
        target_type="ROLE",
        title="관리자 공지",
    )
    defaults.update(kwargs)
    notif = Notification(**defaults)
    db_session.add(notif)
    db_session.flush()
    return notif


def _states(notif):
    return (
        db_session.query(NotificationUserState)
        .filter_by(notification_id=notif.id)
        .all()
    )


def _created_events(notif):
    return (
        db_session.query(NotificationEvent)
        .filter_by(
            notification_id=notif.id, event_type=NotificationEventType.CREATED
        )
        .all()
    )


# ---------------------------------------------------------------------------
# T1: 활성 ADMIN 전원 수신 / 비활성 제외
# ---------------------------------------------------------------------------

def test_role_targets_all_active_users_of_that_role(db):
    """ADMIN 알림은 활성 ADMIN 전원에게 target_role source 로 도달한다."""
    admin1 = _mk_user("role_admin1", "관리자1", role="ADMIN")
    admin2 = _mk_user("role_admin2", "관리자2", role="admin")  # 소문자도 같은 역할
    inactive_admin = _mk_user("role_admin_off", "퇴사관리자", role="ADMIN", is_active=False)
    viewer = _mk_user("role_viewer", "일반", role="VIEWER")

    notif = _mk_notification(target_role="ADMIN")

    result = resolve_recipients_for_notification(db, notif)

    assert result == sorted(
        [
            (admin1.id, NotificationRecipientSource.TARGET_ROLE),
            (admin2.id, NotificationRecipientSource.TARGET_ROLE),
        ]
    )
    recipient_ids = {uid for uid, _ in result}
    assert inactive_admin.id not in recipient_ids
    assert viewer.id not in recipient_ids


# ---------------------------------------------------------------------------
# T2: 좁은 경로 우선
# ---------------------------------------------------------------------------

def test_target_user_overrides_role_source(db):
    """ADMIN 이면서 직접 지정도 된 사용자는 더 좁은 target_user 로 기록된다."""
    admin = _mk_user("role_ovr_admin", "관리자", role="ADMIN")
    other_admin = _mk_user("role_ovr_admin2", "관리자2", role="ADMIN")

    notif = _mk_notification(target_role="ADMIN", target_user_id=admin.id)

    source_by_user = dict(resolve_recipients_for_notification(db, notif))

    assert source_by_user[admin.id] == NotificationRecipientSource.TARGET_USER
    assert source_by_user[other_admin.id] == NotificationRecipientSource.TARGET_ROLE


# ---------------------------------------------------------------------------
# T3: 팬아웃 = state N개 + created 이벤트 N건, 재호출 시 중복 없음
# ---------------------------------------------------------------------------

def test_role_fan_out_creates_states_and_is_idempotent(db):
    """ROLE 알림 팬아웃은 수신자 수만큼 state/event 를 만들고 재호출에 무반응이다."""
    admins = [
        _mk_user(f"role_fan_admin{idx}", f"관리자{idx}", role="ADMIN")
        for idx in range(3)
    ]
    _mk_user("role_fan_viewer", "일반", role="VIEWER")
    actor = _mk_user("role_fan_actor", "작성자", role="MANAGER")

    notif = _mk_notification(target_role="ADMIN")

    created = fan_out_new_notification(db, notif, actor_user_id=actor.id)

    assert len(created) == len(admins)
    assert {s.user_id for s in created} == {a.id for a in admins}
    assert {s.recipient_source for s in created} == {
        NotificationRecipientSource.TARGET_ROLE
    }
    assert len(_states(notif)) == len(admins)
    assert len(_created_events(notif)) == len(admins)

    again = fan_out_new_notification(db, notif, actor_user_id=actor.id)

    assert again == []
    assert len(_states(notif)) == len(admins)
    assert len(_created_events(notif)) == len(admins)


# ---------------------------------------------------------------------------
# T4: 회귀 가드 — target_role NULL 인 기존 알림
# ---------------------------------------------------------------------------

def test_null_target_role_keeps_legacy_paths_unchanged(db):
    """target_role 이 없는 기존 알림은 팀/이름/전체 경로 그대로 동작한다."""
    admin = _mk_user("role_null_admin", "관리자", role="ADMIN")
    cs_user = _mk_user("role_null_cs", "김담당", role="VIEWER", team="CS")
    other = _mk_user("role_null_other", "박담당", role="VIEWER", team="SALES")

    team_notif = _mk_notification(target_type="TEAM", target_team="CS")
    assert team_notif.target_role is None
    team_result = resolve_recipients_for_notification(db, team_notif)
    assert team_result == [(cs_user.id, NotificationRecipientSource.TARGET_TEAM)]

    all_notif = _mk_notification(target_type="ALL")
    all_sources = dict(resolve_recipients_for_notification(db, all_notif))
    assert all_sources == {
        admin.id: NotificationRecipientSource.TARGET_ALL,
        cs_user.id: NotificationRecipientSource.TARGET_ALL,
        other.id: NotificationRecipientSource.TARGET_ALL,
    }

    order_notif = _mk_notification(
        target_type="ORDER", target_manager_name="박담당"
    )
    order_result = resolve_recipients_for_notification(db, order_notif)
    assert order_result == [
        (other.id, NotificationRecipientSource.TARGET_MANAGER_NAME)
    ]
def test_badge_resolver_role_branch_matches_state_fanout(db):
    """배지 무효화 resolver 의 ROLE 집합 == state 팬아웃 집합.

    두 함수가 갈라지면 "알림은 왔는데 배지 숫자가 안 바뀐다"(또는 그 반대)가 된다.
    """
    from foms.api.notifications import resolve_notification_recipient_user_ids
    from foms.services.notifications.recipients import fan_out_new_notification

    active = [_mk_user(f"badge_role_a{i}", f"관리자{i}", role="ADMIN") for i in range(2)]
    _mk_user("badge_role_off", "비활성관리자", role="ADMIN", is_active=False)
    _mk_user("badge_role_viewer", "뷰어", role="VIEWER")
    notif = _mk_notification(target_type="ROLE", target_role="ADMIN")

    fanned = {s.user_id for s in fan_out_new_notification(db, notif, actor_user_id=None)}
    resolved = resolve_notification_recipient_user_ids(
        db, target_type="ROLE", target_role="ADMIN", include_admin=False
    )

    assert fanned == {u.id for u in active}
    assert resolved == fanned
