"""Phase 0A: notification_user_states resolver + backfill 테스트.

DB fixture 는 tests/conftest.py 의 `app` 픽스처(in-memory sqlite + create_all)를 사용한다.
"""
import datetime

import pytest
from sqlalchemy.exc import IntegrityError

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
    ensure_user_states,
    resolve_recipients_for_notification,
)
from foms.services.notifications.backfill import (
    compute_read_and_ambiguous,
    process_notification,
)


def _mk_user(username, name, team=None, role="VIEWER", is_active=True):
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
        target_type="ORDER",
        title="t",
    )
    defaults.update(kwargs)
    notif = Notification(**defaults)
    db_session.add(notif)
    db_session.flush()
    return notif


@pytest.fixture
def db(app):
    """conftest `app` 픽스처로 스키마를 만들고 세션을 정리한다."""
    yield db_session
    db_session.rollback()


# ---------------------------------------------------------------------------
# resolver
# ---------------------------------------------------------------------------

def test_resolver_target_user_source(db):
    u = _mk_user("u1", "홍길동")
    notif = _mk_notification(target_type="USER", target_user_id=u.id)
    result = resolve_recipients_for_notification(db, notif)
    assert result == [(u.id, NotificationRecipientSource.TARGET_USER)]


def test_resolver_target_team_source(db):
    a = _mk_user("t1", "A", team="cs")
    b = _mk_user("t2", "B", team="CS")
    _mk_user("t3", "C", team="drawing")
    notif = _mk_notification(target_type="TEAM", target_team="CS")
    result = dict(resolve_recipients_for_notification(db, notif))
    assert result == {
        a.id: NotificationRecipientSource.TARGET_TEAM,
        b.id: NotificationRecipientSource.TARGET_TEAM,
    }


def test_resolver_target_manager_name_source(db):
    a = _mk_user("m1", "김담당", team="cs")
    _mk_user("m2", "다른사람", team="cs")
    notif = _mk_notification(target_type="ORDER", target_manager_name="김담당")
    result = resolve_recipients_for_notification(db, notif)
    assert result == [(a.id, NotificationRecipientSource.TARGET_MANAGER_NAME)]


def test_resolver_target_all_source(db):
    a = _mk_user("a1", "A")
    b = _mk_user("a2", "B")
    notif = _mk_notification(target_type="ALL")
    result = dict(resolve_recipients_for_notification(db, notif))
    assert result == {
        a.id: NotificationRecipientSource.TARGET_ALL,
        b.id: NotificationRecipientSource.TARGET_ALL,
    }


def test_resolver_excludes_inactive(db):
    active = _mk_user("act", "Active", team="cs")
    _mk_user("inact", "Inactive", team="cs", is_active=False)
    notif = _mk_notification(target_type="TEAM", target_team="CS")
    result = resolve_recipients_for_notification(db, notif)
    assert result == [(active.id, NotificationRecipientSource.TARGET_TEAM)]


def test_resolver_dedupes_to_most_specific_source(db):
    # 같은 사용자가 team 과 target_user 양쪽에 해당 -> target_user 채택.
    u = _mk_user("dup", "겹침", team="cs")
    notif = _mk_notification(
        target_type="USER", target_user_id=u.id, target_team="CS"
    )
    result = resolve_recipients_for_notification(db, notif)
    assert result == [(u.id, NotificationRecipientSource.TARGET_USER)]


# ---------------------------------------------------------------------------
# ensure_user_states idempotency
# ---------------------------------------------------------------------------

def test_ensure_user_states_idempotent(db):
    u = _mk_user("e1", "E", team="cs")
    notif = _mk_notification(target_type="TEAM", target_team="CS")
    smap = dict(resolve_recipients_for_notification(db, notif))

    created1 = ensure_user_states(db, notif, smap)
    assert len(created1) == 1
    created2 = ensure_user_states(db, notif, smap)
    assert created2 == []

    rows = db.query(NotificationUserState).filter_by(notification_id=notif.id).all()
    assert len(rows) == 1
    assert rows[0].user_id == u.id


def test_unique_constraint_blocks_duplicate(db):
    u = _mk_user("uc", "UC")
    notif = _mk_notification(target_type="USER", target_user_id=u.id)
    db.add(NotificationUserState(
        notification_id=notif.id, user_id=u.id,
        recipient_source=NotificationRecipientSource.TARGET_USER,
    ))
    db.flush()
    db.add(NotificationUserState(
        notification_id=notif.id, user_id=u.id,
        recipient_source=NotificationRecipientSource.TARGET_USER,
    ))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


# ---------------------------------------------------------------------------
# backfill legacy read preservation
# ---------------------------------------------------------------------------

def test_backfill_read_preserved_for_known_reader(db):
    # 규칙: is_read + read_by_user_id 있고 수신자 -> 그 사용자만 read.
    reader = _mk_user("r1", "Reader", team="cs")
    other = _mk_user("r2", "Other", team="cs")
    read_at = datetime.datetime(2026, 7, 1, 10, 0, 0)
    notif = _mk_notification(
        target_type="TEAM", target_team="CS",
        is_read=True, read_by_user_id=reader.id, read_at=read_at,
    )
    process_notification(db, notif, dry_run=False)

    states = {
        s.user_id: s
        for s in db.query(NotificationUserState).filter_by(notification_id=notif.id)
    }
    assert states[reader.id].read_at == read_at
    assert states[other.id].read_at is None


def test_backfill_read_preserved_for_target_user(db):
    # target_type USER 이고 target_user_id==read_by_user_id -> read 보존.
    u = _mk_user("tu", "TU")
    read_at = datetime.datetime(2026, 7, 2, 9, 0, 0)
    notif = _mk_notification(
        target_type="USER", target_user_id=u.id,
        is_read=True, read_by_user_id=u.id, read_at=read_at,
    )
    process_notification(db, notif, dry_run=False)
    state = db.query(NotificationUserState).filter_by(notification_id=notif.id).one()
    assert state.read_at == read_at


def test_backfill_ambiguous_read_no_expansion(db):
    # is_read=True + read_by_user_id 없음 -> 확대 금지, ambiguous event 1건, states unread.
    _mk_user("g1", "A", team="cs")
    _mk_user("g2", "B", team="cs")
    notif = _mk_notification(
        target_type="TEAM", target_team="CS",
        is_read=True, read_by_user_id=None,
        read_at=datetime.datetime(2026, 7, 3, 8, 0, 0),
    )
    process_notification(db, notif, dry_run=False)

    states = db.query(NotificationUserState).filter_by(notification_id=notif.id).all()
    assert len(states) == 2
    assert all(s.read_at is None for s in states)

    events = db.query(NotificationEvent).filter_by(
        notification_id=notif.id,
        event_type=NotificationEventType.LEGACY_READ_AMBIGUOUS,
    ).all()
    assert len(events) == 1


def test_compute_read_and_ambiguous_reader_not_recipient(db):
    # read_by_user_id 가 수신자가 아니면 read 확대 없음, ambiguous 아님.
    stranger = _mk_user("s1", "Stranger", team="drawing")
    member = _mk_user("s2", "Member", team="cs")
    notif = _mk_notification(
        target_type="TEAM", target_team="CS",
        is_read=True, read_by_user_id=stranger.id,
        read_at=datetime.datetime(2026, 7, 4, 7, 0, 0),
    )
    source_by_user = {member.id: NotificationRecipientSource.TARGET_TEAM}
    read_map, ambiguous = compute_read_and_ambiguous(notif, source_by_user)
    assert read_map == {}
    assert ambiguous is False


# ---------------------------------------------------------------------------
# backfill idempotency (run twice -> no dup)
# ---------------------------------------------------------------------------

def test_backfill_process_twice_no_duplicates(db):
    reader = _mk_user("d1", "Reader", team="cs")
    _mk_user("d2", "Other", team="cs")
    notif = _mk_notification(
        target_type="TEAM", target_team="CS",
        is_read=True, read_by_user_id=reader.id,
        read_at=datetime.datetime(2026, 7, 1, 10, 0, 0),
    )
    r1 = process_notification(db, notif, dry_run=False)
    r2 = process_notification(db, notif, dry_run=False)
    assert r1["states_created"] == 2
    assert r2["states_created"] == 0

    states = db.query(NotificationUserState).filter_by(notification_id=notif.id).all()
    assert len(states) == 2
    backfilled = db.query(NotificationEvent).filter_by(
        notification_id=notif.id,
        event_type=NotificationEventType.STATE_BACKFILLED,
    ).all()
    assert len(backfilled) == 2


def test_backfill_ambiguous_event_not_duplicated(db):
    _mk_user("am1", "A", team="cs")
    notif = _mk_notification(
        target_type="TEAM", target_team="CS",
        is_read=True, read_by_user_id=None,
    )
    process_notification(db, notif, dry_run=False)
    process_notification(db, notif, dry_run=False)
    events = db.query(NotificationEvent).filter_by(
        notification_id=notif.id,
        event_type=NotificationEventType.LEGACY_READ_AMBIGUOUS,
    ).all()
    assert len(events) == 1
