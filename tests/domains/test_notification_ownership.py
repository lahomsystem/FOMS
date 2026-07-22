"""Phase 0B: notification_user_states 기반 소유권/보관/확인 + write guard 테스트.

DB fixture 는 tests/conftest.py 의 `app`(in-memory sqlite) + `client` 를 사용한다.
"""
import datetime

import pytest

from db import db_session
from models import (
    Notification,
    NotificationEvent,
    NotificationEventType,
    NotificationRecipientSource,
    NotificationUserState,
    Order,
    User,
)

WRITE_HEADERS = {"X-FOMS-Notification-Write": "1"}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

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
    defaults = dict(notification_type="ANNOUNCEMENT", target_type="ORDER", title="t")
    defaults.update(kwargs)
    notif = Notification(**defaults)
    db_session.add(notif)
    db_session.flush()
    return notif


def _mk_state(notif, user, source=NotificationRecipientSource.TARGET_TEAM, **kwargs):
    state = NotificationUserState(
        notification_id=notif.id,
        user_id=user.id,
        recipient_source=source,
        **kwargs,
    )
    db_session.add(state)
    db_session.flush()
    return state


def _mk_order(manager_name="관련영업", **kwargs):
    order = Order(
        received_date=datetime.date(2026, 7, 4),
        customer_name=kwargs.get("customer_name", "고객"),
        phone="010-0000-0000",
        address="Seoul",
        product="가구",
        status=kwargs.get("status", "ERPORDER"),
        manager_name=manager_name,
        is_erp_order=True,
    )
    db_session.add(order)
    db_session.flush()
    return order


def _get_state(pk):
    """요청 teardown 후 detach 를 피하기 위해 fresh 세션으로 재조회."""
    return db_session.get(NotificationUserState, pk)


def _login(client, user):
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


@pytest.fixture
def db(app):
    yield db_session
    db_session.rollback()


# ---------------------------------------------------------------------------
# 소유권: 타 사용자 알림에 대한 상태 변경 차단
# ---------------------------------------------------------------------------

def test_read_other_users_notification_returns_404(client, db):
    a = _mk_user("own_a", "A")
    b = _mk_user("own_b", "B")
    notif = _mk_notification(target_type="USER", target_user_id=a.id)
    _mk_state(notif, a, source=NotificationRecipientSource.TARGET_USER)

    _login(client, b)
    resp = client.post(f"/erp/api/notifications/{notif.id}/read", headers=WRITE_HEADERS)
    assert resp.status_code == 404


def test_archive_other_users_notification_returns_404(client, db):
    a = _mk_user("arc_a", "A")
    b = _mk_user("arc_b", "B")
    notif = _mk_notification(target_type="USER", target_user_id=a.id)
    _mk_state(notif, a, source=NotificationRecipientSource.TARGET_USER)

    _login(client, b)
    resp = client.post(f"/erp/api/notifications/{notif.id}/archive", headers=WRITE_HEADERS)
    assert resp.status_code == 404


def test_ack_other_users_notification_returns_404(client, db):
    a = _mk_user("ack_a", "A")
    b = _mk_user("ack_b", "B")
    notif = _mk_notification(target_type="USER", target_user_id=a.id, is_urgent=True)
    _mk_state(notif, a, source=NotificationRecipientSource.TARGET_USER)

    _login(client, b)
    resp = client.post(f"/erp/api/notifications/{notif.id}/ack", headers=WRITE_HEADERS)
    assert resp.status_code == 404


def test_shared_notification_read_does_not_affect_other_state(client, db):
    a = _mk_user("sh_a", "A", team="cs")
    b = _mk_user("sh_b", "B", team="cs")
    notif = _mk_notification(target_type="TEAM", target_team="CS")
    state_a = _mk_state(notif, a)
    state_b = _mk_state(notif, b)
    sa_id, sb_id, notif_id = state_a.id, state_b.id, notif.id

    _login(client, a)
    resp = client.post(f"/erp/api/notifications/{notif_id}/read", headers=WRITE_HEADERS)
    assert resp.status_code == 200

    assert _get_state(sa_id).read_at is not None
    assert _get_state(sb_id).read_at is None
    # 공유 Notification legacy 필드는 오염되지 않는다.
    assert db.get(Notification, notif_id).is_read is False


def test_read_all_only_updates_current_user(client, db):
    a = _mk_user("ra_a", "A", team="cs")
    b = _mk_user("ra_b", "B", team="cs")
    n1 = _mk_notification(target_type="TEAM", target_team="CS")
    n2 = _mk_notification(target_type="TEAM", target_team="CS")
    sa1_id = _mk_state(n1, a).id
    sa2_id = _mk_state(n2, a).id
    sb1_id = _mk_state(n1, b).id

    _login(client, a)
    resp = client.post("/erp/api/notifications/read-all", headers=WRITE_HEADERS)
    assert resp.status_code == 200
    assert resp.get_json()["count"] == 2

    assert _get_state(sa1_id).read_at is not None and _get_state(sa2_id).read_at is not None
    assert _get_state(sb1_id).read_at is None


def test_archive_all_only_updates_current_user(client, db):
    a = _mk_user("aa_a", "A", team="cs")
    b = _mk_user("aa_b", "B", team="cs")
    n1 = _mk_notification(target_type="TEAM", target_team="CS")
    sa_id = _mk_state(n1, a).id
    sb_id = _mk_state(n1, b).id

    _login(client, a)
    resp = client.post("/erp/api/notifications/archive-all", headers=WRITE_HEADERS)
    assert resp.status_code == 200

    assert _get_state(sa_id).archived_at is not None
    assert _get_state(sb_id).archived_at is None


def test_ack_is_independent_of_read(client, db):
    a = _mk_user("ind_a", "A")
    notif = _mk_notification(target_type="USER", target_user_id=a.id, is_urgent=True)
    state_id = _mk_state(notif, a, source=NotificationRecipientSource.TARGET_USER).id
    notif_id = notif.id

    _login(client, a)
    # read 후에는 ack_at 이 여전히 None.
    client.post(f"/erp/api/notifications/{notif_id}/read", headers=WRITE_HEADERS)
    st = _get_state(state_id)
    assert st.read_at is not None
    assert st.ack_at is None
    prev_read = st.read_at

    # ack 후 ack_at 채워지고 read_at 은 그대로.
    client.post(f"/erp/api/notifications/{notif_id}/ack", headers=WRITE_HEADERS)
    st = _get_state(state_id)
    assert st.ack_at is not None
    assert st.read_at == prev_read


# ---------------------------------------------------------------------------
# delete-all: 관리자 전용
# ---------------------------------------------------------------------------

def test_delete_all_non_admin_returns_403(client, db):
    viewer = _mk_user("del_v", "Viewer", role="VIEWER")
    _login(client, viewer)
    resp = client.post("/erp/api/notifications/delete-all", headers=WRITE_HEADERS)
    assert resp.status_code == 403


def test_delete_all_admin_allowed(client, db):
    admin = _mk_user("del_admin", "Admin", role="ADMIN")
    _mk_notification(target_type="ALL")
    _login(client, admin)
    resp = client.post("/erp/api/notifications/delete-all", headers=WRITE_HEADERS)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# write guard
# ---------------------------------------------------------------------------

def test_write_missing_header_returns_403(client, db):
    a = _mk_user("wg_a", "A")
    notif = _mk_notification(target_type="USER", target_user_id=a.id)
    _mk_state(notif, a, source=NotificationRecipientSource.TARGET_USER)

    _login(client, a)
    resp = client.post(f"/erp/api/notifications/{notif.id}/read")
    assert resp.status_code == 403


def test_write_cross_origin_returns_403(client, db):
    a = _mk_user("wg_b", "A")
    notif = _mk_notification(target_type="USER", target_user_id=a.id)
    _mk_state(notif, a, source=NotificationRecipientSource.TARGET_USER)

    _login(client, a)
    headers = dict(WRITE_HEADERS)
    headers["Origin"] = "http://evil.example.com"
    resp = client.post(f"/erp/api/notifications/{notif.id}/read", headers=headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# urgent-targets
# ---------------------------------------------------------------------------

def test_urgent_targets_unrelated_caller_403(client, db):
    order = _mk_order(manager_name="담당자")
    unrelated = _mk_user("ut_unrel", "무관", role="VIEWER")
    _login(client, unrelated)
    resp = client.get(f"/erp/api/orders/{order.id}/urgent-targets")
    assert resp.status_code == 403


def test_urgent_targets_excludes_inactive_and_self(client, db):
    order = _mk_order(manager_name="담당자")
    caller = _mk_user("ut_caller", "담당자", role="VIEWER")  # 이름 매칭 → 관련자
    admin = _mk_user("ut_admin", "관리자", role="ADMIN")
    _mk_user("ut_inactive", "담당자비활성", role="ADMIN", is_active=False)

    _login(client, caller)
    resp = client.get(f"/erp/api/orders/{order.id}/urgent-targets")
    assert resp.status_code == 200
    data = resp.get_json()
    ids = {t["id"] for t in data["targets"]}
    assert admin.id in ids           # 관리자는 항상 후보
    assert caller.id not in ids      # 자기 자신 제외
    assert all(t["id"] != _u_id_by_username("ut_inactive") for t in data["targets"])


def _u_id_by_username(username):
    row = db_session.query(User.id).filter(User.username == username).first()
    return row[0] if row else None


def test_urgent_targets_includes_unrelated_active_user(client, db):
    """대상 목록은 주문 관련성과 무관하게 활성 사용자 전원을 연다(팀 드롭다운 UI 대응)."""
    order = _mk_order(manager_name="담당자")
    caller = _mk_user("ut_incl_caller", "담당자", role="VIEWER")  # 이름 매칭 → 관련자(sender 통과)
    outsider = _mk_user("ut_incl_out", "무관동료", role="STAFF", team="PRODUCTION")

    _login(client, caller)
    resp = client.get(f"/erp/api/orders/{order.id}/urgent-targets")
    assert resp.status_code == 200
    data = resp.get_json()
    labels = {t["id"]: t.get("team_label") for t in data["targets"]}
    assert outsider.id in labels          # 주문과 무관해도 후보에 포함
    assert labels[outsider.id] == "생산팀"  # 팀 라벨은 TEAMS SSOT 반영


def test_urgent_targets_unknown_team_labeled_gita(client, db):
    """팀 미등록/미상 사용자는 '기타' 라벨로 노출(조용한 누락 금지)."""
    order = _mk_order(manager_name="담당자")
    caller = _mk_user("ut_gita_caller", "담당자", role="ADMIN")
    noteam = _mk_user("ut_gita_noteam", "무팀원", role="VIEWER", team=None)

    _login(client, caller)
    resp = client.get(f"/erp/api/orders/{order.id}/urgent-targets")
    assert resp.status_code == 200
    data = resp.get_json()
    labels = {t["id"]: t.get("team_label") for t in data["targets"]}
    assert labels.get(noteam.id) == "기타"


# ---------------------------------------------------------------------------
# urgent-mention 강화
# ---------------------------------------------------------------------------


def test_urgent_mention_unrelated_target_succeeds(client, db):
    """대상 게이트 개방: 주문과 무관한 활성 사용자도 멘션 가능(대상 목록과 계약 일치)."""
    order = _mk_order(manager_name="담당자")
    caller = _mk_user("um_open_caller", "관리자", role="ADMIN")  # sender 게이트 통과
    outsider = _mk_user("um_open_out", "무관동료", role="VIEWER")

    _login(client, caller)
    resp = client.post(
        f"/erp/api/orders/{order.id}/urgent-mention",
        json={"target_user_id": outsider.id, "message": "확인 부탁"},
        headers=WRITE_HEADERS,
    )
    assert resp.status_code == 200

def test_urgent_mention_unauthorized_caller_403(client, db):
    order = _mk_order(manager_name="담당자")
    caller = _mk_user("um_unrel", "무관", role="VIEWER")
    target = _mk_user("um_tgt", "담당자", role="VIEWER")
    _login(client, caller)
    resp = client.post(
        f"/erp/api/orders/{order.id}/urgent-mention",
        json={"target_user_id": target.id},
        headers=WRITE_HEADERS,
    )
    assert resp.status_code == 403


def test_urgent_mention_self_returns_400(client, db):
    order = _mk_order(manager_name="담당자")
    admin = _mk_user("um_self", "관리자", role="ADMIN")
    _login(client, admin)
    resp = client.post(
        f"/erp/api/orders/{order.id}/urgent-mention",
        json={"target_user_id": admin.id},
        headers=WRITE_HEADERS,
    )
    assert resp.status_code == 400


def test_urgent_mention_message_too_long_returns_400(client, db):
    order = _mk_order(manager_name="담당자")
    admin = _mk_user("um_msg_admin", "관리자", role="ADMIN")
    target = _mk_user("um_msg_tgt", "대상", role="MANAGER")
    _login(client, admin)
    resp = client.post(
        f"/erp/api/orders/{order.id}/urgent-mention",
        json={"target_user_id": target.id, "message": "x" * 501},
        headers=WRITE_HEADERS,
    )
    assert resp.status_code == 400


def test_urgent_mention_creates_states(client, db):
    order = _mk_order(manager_name="담당자")
    admin = _mk_user("um_ok_admin", "관리자", role="ADMIN")
    target = _mk_user("um_ok_tgt", "대상", role="MANAGER")
    _login(client, admin)
    resp = client.post(
        f"/erp/api/orders/{order.id}/urgent-mention",
        json={"target_user_id": target.id, "message": "빨리요"},
        headers=WRITE_HEADERS,
    )
    assert resp.status_code == 200

    state = (
        db.query(NotificationUserState)
        .filter(NotificationUserState.user_id == target.id)
        .first()
    )
    assert state is not None
    created = (
        db.query(NotificationEvent)
        .filter(
            NotificationEvent.recipient_user_id == target.id,
            NotificationEvent.event_type == NotificationEventType.CREATED,
        )
        .first()
    )
    assert created is not None


# ---------------------------------------------------------------------------
# send: 수신자 state 자동 생성
# ---------------------------------------------------------------------------

def test_send_creates_states(client, db):
    admin = _mk_user("send_admin", "관리자", role="ADMIN")
    recipient = _mk_user("send_rcpt", "수신자", role="VIEWER")
    recipient_id = recipient.id
    _login(client, admin)
    resp = client.post(
        "/erp/api/notifications/send",
        json={"title": "공지", "message": "본문", "target_type": "USER", "target_user_ids": [recipient_id]},
        headers=WRITE_HEADERS,
    )
    assert resp.status_code == 200

    state = (
        db.query(NotificationUserState)
        .filter(NotificationUserState.user_id == recipient_id)
        .first()
    )
    assert state is not None


# ---------------------------------------------------------------------------
# personal_board unread 가 user_states 기준
# ---------------------------------------------------------------------------

def test_personal_board_unread_uses_states(db):
    from foms.api.personal_board import _unread_notifications_count

    user = _mk_user("pb_u", "PB", team="cs")
    n1 = _mk_notification(target_type="TEAM", target_team="CS")
    n2 = _mk_notification(target_type="TEAM", target_team="CS")
    _mk_state(n1, user)  # unread
    _mk_state(n2, user, read_at=datetime.datetime.now())  # read
    db.flush()

    assert _unread_notifications_count(db, user, user.id) == 1
