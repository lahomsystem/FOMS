"""긴급 호출 보낸 사람 기준 상한 — 주문이 있든 없든 같은 상한.

SPEC ``docs/specs/2026-10-19-urgent-call-send-limit_SPEC.md`` §3·§4.
- 세는 단위는 호출 1회(받는 사람 수 아님), 보낸 사람마다 따로 센다.
- 넘으면 429 + ``{'success': False, 'error': ...}`` 이고 알림 행이 늘지 않는다.
- 창(분)이 지난 호출은 세지 않는다. 기존 주문당 상한은 그대로다.
"""
from __future__ import annotations

import datetime

from foms.api.notifications import URGENT_MENTION_RATE_PER_HOUR as _PER_ORDER  # 기존 주문당 상한
from foms.services.notifications.urgent_call_limit import (
    URGENT_CALL_SENDER_LIMIT,
    URGENT_CALL_SENDER_WINDOW_MINUTES,
    urgent_sender_limit_message,
)
from tests.domains.test_urgent_call_global import (
    WRITE_HEADERS, Notification, User, _call, _login, _mk_order, _mk_user, db,
)


def _multi(client, ids, **extra):
    return client.post("/erp/api/urgent-call", json={
        "target_user_ids": ids, "message": "확인 부탁", **extra,
    }, headers=WRITE_HEADERS)


def _sent_count(db, sender_id):
    return db.query(Notification).filter(Notification.created_by_user_id == sender_id).count()


def _assert_sender_limited(resp):
    assert resp.status_code == 429, resp.get_data(as_text=True)
    body = resp.get_json()
    assert body["success"] is False
    assert body["error"] == urgent_sender_limit_message()
    assert body["message"] == body["error"]  # 화면(urgent-call.js)이 읽는 키도 같은 문구


def test_no_order_calls_over_sender_limit_are_429_without_writes(client, db):
    sender = _mk_user("ucsl_no_sender", "보낸이", role="ADMIN")
    target = _mk_user("ucsl_no_target", "받는이")
    sid, tid = sender.id, target.id
    _login(client, sender)
    for i in range(URGENT_CALL_SENDER_LIMIT):
        r = _call(client, tid, f"호출 {i}")
        assert r.status_code == 200, (i, r.get_data(as_text=True))
    _assert_sender_limited(_call(client, tid, "넘침"))
    assert _sent_count(db, sid) == URGENT_CALL_SENDER_LIMIT


def test_order_and_no_order_calls_share_one_sender_limit(client, db):
    """주문 있는 호출과 없는 호출을 합쳐 센다 — 주문당 상한에는 닿지 않게 주문을 나눠 싣는다."""
    with_order = URGENT_CALL_SENDER_LIMIT // 2
    orders = [_mk_order().id for _ in range(-(-with_order // _PER_ORDER) + 1)]
    sender = _mk_user("ucsl_mix_sender", "보낸이", role="ADMIN")
    target = _mk_user("ucsl_mix_target", "받는이")
    sid, tid = sender.id, target.id
    _login(client, sender)
    for i in range(with_order):
        r = _call(client, tid, f"주문 {i}", order_id=orders[i // _PER_ORDER])
        assert r.status_code == 200, (i, r.get_data(as_text=True))
    for i in range(URGENT_CALL_SENDER_LIMIT - with_order):
        r = _call(client, tid, f"주문 없이 {i}")
        assert r.status_code == 200, (i, r.get_data(as_text=True))
    _assert_sender_limited(_call(client, tid, "주문 없이 넘침"))
    _assert_sender_limited(_call(client, tid, "새 주문도 넘침", order_id=orders[-1]))
    assert _sent_count(db, sid) == URGENT_CALL_SENDER_LIMIT


def test_each_sender_is_counted_separately(client, db):
    first = _mk_user("ucsl_sep_a", "첫째", role="ADMIN")
    second = _mk_user("ucsl_sep_b", "둘째", role="STAFF")
    target = _mk_user("ucsl_sep_target", "받는이")
    second_id, tid = second.id, target.id
    _login(client, first)
    for i in range(URGENT_CALL_SENDER_LIMIT):
        assert _call(client, tid, f"첫째 {i}").status_code == 200
    _assert_sender_limited(_call(client, tid, "첫째 넘침"))
    _login(client, db.get(User, second_id))
    resp = _call(client, tid, "둘째 첫 호출")
    assert resp.status_code == 200, resp.get_data(as_text=True)


def test_multi_recipient_call_counts_once(client, db):
    """한 번에 여러 명 = 호출 1회. 받는 사람 수로 세면 팀 전체 호출 한 번이 막힌다."""
    sender = _mk_user("ucsl_multi_sender", "보낸이", role="ADMIN")
    ids = [_mk_user(f"ucsl_multi_{i}", f"받는이{i}").id for i in range(3)]
    sid = sender.id
    _login(client, sender)
    for i in range(URGENT_CALL_SENDER_LIMIT):
        r = _multi(client, ids)
        assert r.status_code == 200, (i, r.get_data(as_text=True))
    _assert_sender_limited(_multi(client, ids))
    assert _sent_count(db, sid) == URGENT_CALL_SENDER_LIMIT * len(ids)


def test_one_call_rows_share_created_at(client, db):
    """상한은 서로 다른 created_at 을 센다 — 한 호출의 행은 행마다 기본값이 아니라 같은 발송 시각이다."""
    from foms.api.notifications import _create_urgent_receipts

    sender = _mk_user("ucsl_ts_sender", "보낸이", role="ADMIN")
    targets = [_mk_user(f"ucsl_ts_{i}", f"받는이{i}") for i in range(3)]
    sent_at = datetime.datetime(2026, 10, 19, 1, 2, 3, 456789)
    receipts = _create_urgent_receipts(db, sender, targets, "제목", "사유", None, sent_at)
    assert [notif.created_at for notif, _event in receipts] == [sent_at] * len(targets)


def test_calls_older_than_window_are_not_counted(client, db):
    sender = _mk_user("ucsl_win_sender", "보낸이", role="ADMIN")
    target = _mk_user("ucsl_win_target", "받는이")
    sid, tid = sender.id, target.id
    _login(client, sender)
    for i in range(URGENT_CALL_SENDER_LIMIT):
        assert _call(client, tid, f"호출 {i}").status_code == 200
    _assert_sender_limited(_call(client, tid, "넘침"))
    shift = datetime.timedelta(minutes=URGENT_CALL_SENDER_WINDOW_MINUTES + 1)
    for notif in db.query(Notification).filter(Notification.created_by_user_id == sid).all():
        notif.created_at = notif.created_at - shift
    db.commit()
    resp = _call(client, tid, "창 지난 뒤")
    assert resp.status_code == 200, resp.get_data(as_text=True)
