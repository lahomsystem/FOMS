"""협력사 명세서 발행 알림(사용자 결정 2026-11-05, 설계서 2026-11-03 0.1-13).

출고 전날까지 발행 안 된 협력사 주문을 KST 9시 이후 우리 CS 에 주문마다 한 번 알린다. 옵션이 없는 주문도 알린다.
대조군: 9시 전 · 발행한 주문 · 출고일이 먼 주문 · 오래 지난 주문은 알리지 않는다. 두 번 돌려도 한 번만.
"""
from __future__ import annotations

import datetime

from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.notifications import push_sender
from foms.services.partners import statement_reminder as reminder
from models import Notification, Order
from tests.security.partner_fixtures import _PAYLOAD, _create, world  # noqa: F401
from tests.security.test_partner_item_options import _item, priced  # noqa: F401
from tests.security.test_partner_statements import API, _confirmed_order, _cs, _draft

NOW = datetime.datetime(2026, 11, 9, 9, 5, tzinfo=datetime.timezone(datetime.timedelta(hours=9)))


def _bare_order(app, w, date: str) -> int:
    """옵션을 안 고른 협력사 주문(운영 11-05 에 막혀 있던 모양)."""
    resp = _create(app, w["partner_a"], {**_PAYLOAD, "items": [_item(lines=[{"key": "r4", "qty": 1}])]})
    oid = resp.get_json()["data"]["order_id"]
    order = db_session.get(Order, oid)
    sd = dict(order.structured_data)
    sd["schedule"] = {**(sd.get("schedule") or {}), "construction": {"date": date}}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    return oid


def _due_ids():
    return sorted(n.order_id for n in db_session.query(Notification).filter(
        Notification.notification_type == reminder.NOTIFICATION_TYPE).all())


def test_reminds_unissued_once_per_order_after_nine(app, priced):
    tomorrow = _confirmed_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}])], date="2026-11-10")
    no_options = _bare_order(app, priced, "2026-11-08")
    far = _bare_order(app, priced, "2026-11-20")
    old = _bare_order(app, priced, "2026-10-20")
    issued = _confirmed_order(app, priced, [_item(lines=[{"key": "r4", "qty": 1}])], date="2026-11-10")
    client = _cs(app)
    data = _draft(client, issued)
    assert client.post(f"{API}/{data['id']}/issue", json={"version": data["version"]}).status_code == 200

    early = reminder.remind_unissued_partner_statements(db_session, now=NOW.replace(hour=8, minute=59))
    assert early["reminded"] == 0 and _due_ids() == []

    got = reminder.remind_unissued_partner_statements(db_session, now=NOW)
    db_session.commit()
    assert got["checked"] == 2 and got["reminded"] == 2
    assert _due_ids() == sorted([tomorrow, no_options])
    assert far not in _due_ids() and old not in _due_ids() and issued not in _due_ids()
    note = db_session.query(Notification).filter(Notification.order_id == tomorrow,
                                             Notification.notification_type == reminder.NOTIFICATION_TYPE).one()
    assert note.target_team == "CS" and "내일 출고(11월 10일)" in note.message

    again = reminder.remind_unissued_partner_statements(db_session, now=NOW + datetime.timedelta(hours=2))
    db_session.commit()
    assert again["reminded"] == 0 and len(_due_ids()) == 2


def test_new_ship_date_reminds_again(app, priced):
    oid = _bare_order(app, priced, "2026-11-10")
    reminder.remind_unissued_partner_statements(db_session, now=NOW)
    db_session.commit()
    order = db_session.get(Order, oid)
    sd = dict(order.structured_data)
    sd["schedule"] = {**sd["schedule"], "construction": {"date": "2026-11-09"}}
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    got = reminder.remind_unissued_partner_statements(db_session, now=NOW)
    db_session.commit()
    assert got["reminded"] == 1 and _due_ids() == [oid, oid]


def test_due_type_gets_phone_push():
    assert reminder.NOTIFICATION_TYPE in push_sender._DEFAULT_P1_TYPES
