"""안 보낸 마법사 초안 미등록 알림 (2026-10-26 설계서
docs/plans/2026-10-26-wizard-unsent-draft-reminder-spec.md).

고객명·연락처까지 적고 [주문 등록] 없이 떠난 초안은 60분 뒤 작성자에게 1회 알린다.
같은 연락처 주문이 이미 있으면 알리지 않는다. 알렸다는 표시가 "발송함" 판정에 섞이면
만료돼도 안 지워지므로 그 경계도 함께 지킨다.
"""

from __future__ import annotations

import datetime

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.notifications import draft_send_reminder as reminder
from foms.services.notifications.push_sender import _DEFAULT_P1_TYPES
from foms.services.order_draft_service import _SEND_KINDS, list_open_drafts
from models import Notification, Order, OrderDraft, User
from tools.cron import cleanup_order_drafts
from tools.cron.cleanup_order_drafts import run as run_cleanup

NOW = datetime.datetime(2026, 10, 26, 5, 0, 0)


def _user(username: str) -> User:
    user = User(username=username, password=generate_password_hash("pass"), role="STAFF",
                name="작성자")
    db_session.add(user)
    db_session.commit()
    return user


def _draft(user: User, key: str, *, idle_minutes: int, name="이화원",
           phone="010-0000-0000", history=None, expired=False) -> OrderDraft:
    touched = NOW - datetime.timedelta(minutes=idle_minutes)
    draft = OrderDraft(
        user_id=user.id,
        draft_key=key,
        step=2,
        payload={"schema_version": 1, "step": 2,
                 "data": {"customer_name": name, "phone": phone}},
        created_at=touched,
        updated_at=touched,
        expires_at=NOW + datetime.timedelta(days=-1 if expired else 7),
        send_history=history,
    )
    db_session.add(draft)
    db_session.commit()
    return draft


def _order(phone: str, created_at: datetime.datetime, deleted=False) -> None:
    db_session.add(Order(
        received_date="2026-10-26", customer_name="이화원", phone=phone,
        address="노원 테스트로 1", product="붙박이장", created_at=created_at,
        deleted_at="2026-10-26 04:00:00" if deleted else None,
    ))
    db_session.commit()


def _notes(user_id: int) -> list[Notification]:
    return (
        db_session.query(Notification)
        .filter(Notification.target_user_id == user_id,
                Notification.notification_type == reminder.IDLE_NOTIFICATION_TYPE)
        .all()
    )


def test_named_draft_reminded_once_after_60_minutes(app):
    owner = _user("idle-1")
    draft = _draft(owner, "new.i1", idle_minutes=61)
    before_updated = draft.updated_at

    first = reminder.remind_idle_unsent_drafts(db_session, now=NOW)
    db_session.commit()
    second = reminder.remind_idle_unsent_drafts(db_session, now=NOW)
    db_session.commit()

    assert first["owner_reminded"] == 1
    assert second["owner_reminded"] == 0
    notes = _notes(owner.id)
    assert len(notes) == 1
    assert "이화원" in notes[0].message and "작성 중" in notes[0].message
    db_session.expire_all()
    saved = db_session.get(OrderDraft, draft.id)
    # 서버 쓰기가 If-Match 토큰(updated_at)을 흔들면 다음 autosave 가 409 로 튕긴다.
    assert saved.updated_at == before_updated
    assert saved.send_history[reminder.IDLE_REMINDER_KEY]["owner_at"]


def test_not_reminded_before_60_minutes_or_after_lookback(app):
    owner = _user("idle-2")
    _draft(owner, "new.i2a", idle_minutes=30)
    _draft(owner, "new.i2b", idle_minutes=60 * 25)

    result = reminder.remind_idle_unsent_drafts(db_session, now=NOW)

    assert result["owner_reminded"] == 0
    assert _notes(owner.id) == []


def test_name_or_phone_missing_is_not_reminded(app):
    owner = _user("idle-3")
    _draft(owner, "new.i3a", idle_minutes=90, name="")
    _draft(owner, "new.i3b", idle_minutes=90, phone="")

    result = reminder.remind_idle_unsent_drafts(db_session, now=NOW)

    assert result["owner_reminded"] == 0


def test_same_phone_order_skips_but_deleted_order_does_not(app):
    owner = _user("idle-4")
    _draft(owner, "new.i4a", idle_minutes=90, phone="010-1111-2222")
    _order("01011112222", NOW - datetime.timedelta(minutes=80))
    _draft(owner, "new.i4b", idle_minutes=90, phone="010-3333-4444")
    _order("010-3333-4444", NOW - datetime.timedelta(minutes=80), deleted=True)

    result = reminder.remind_idle_unsent_drafts(db_session, now=NOW)

    # 같은 연락처 주문이 살아 있는 i4a 는 건너뛰고, 그 주문이 지워진 i4b 만 알린다.
    assert result["owner_reminded"] == 1
    assert len(_notes(owner.id)) == 1


def test_sent_draft_is_left_to_sent_reminder(app):
    owner = _user("idle-5")
    pushed = {"channeltalk_push_measure_room": {
        "pushed": True, "sent_at": (NOW - datetime.timedelta(minutes=90)).isoformat()}}
    _draft(owner, "new.i5", idle_minutes=90, history=pushed)

    result = reminder.remind_idle_unsent_drafts(db_session, now=NOW)

    assert result["owner_reminded"] == 0


def test_saving_again_after_reminder_reminds_again(app):
    owner = _user("idle-6")
    draft = _draft(owner, "new.i6", idle_minutes=61)
    reminder.remind_idle_unsent_drafts(db_session, now=NOW)
    db_session.commit()

    draft.updated_at = NOW + datetime.timedelta(minutes=5)
    db_session.commit()
    later = NOW + datetime.timedelta(minutes=66)
    result = reminder.remind_idle_unsent_drafts(db_session, now=later)

    assert result["owner_reminded"] == 1


def test_reminder_mark_is_not_counted_as_sent(app):
    """알렸다는 표시만 있는 초안은 만료되면 평소처럼 지워지고 '작성 중' 목록에서도 빠진다."""
    owner = _user("idle-7")
    marked = _draft(owner, "new.i7", idle_minutes=61, expired=True,
                    history={reminder.IDLE_REMINDER_KEY: {"owner_at": NOW.isoformat()}})
    marked_id = marked.id

    assert list_open_drafts(db_session, owner.id, now=NOW) == []
    scanned, deleted = run_cleanup(execute=True, session=db_session)

    assert (scanned, deleted) == (1, 1)
    db_session.expire_all()
    assert db_session.get(OrderDraft, marked_id) is None


def test_cron_sent_kind_keys_match_app():
    assert set(cleanup_order_drafts.SENT_KIND_KEYS) == set(_SEND_KINDS)


def test_idle_type_is_pushed_to_phone():
    assert reminder.IDLE_NOTIFICATION_TYPE in _DEFAULT_P1_TYPES
