"""AUDIT-GAP-01: AS 방문 일정(``schedule.as_visit``) 보존 + 가능시간 변경 원장 계약.

PC ERP 폼은 ``schedule`` 을 ``{measurement, construction}`` 만으로 조립해 보낸다
(``erp-order-shared.js``). 그런데 ``schedule`` 이 보존(deep-merge) 목록에 없어서, **AS 주문을
ERP 폼으로 한 번 저장할 때마다 ``schedule.as_visit`` 이 통째로 사라졌다** — 고객과 약속한
방문일·시간·가능시간대가 흔적 없이 증발했다.

여기서 고정하는 것 3가지.

* **보존**: 폼이 렌더하지 않는 ``as_visit`` 은 저장을 거쳐도 살아남는다.
* **비우기는 그대로 동작**: 폼이 항상 보내는 ``measurement``/``construction`` 의 날짜·시간은
  빈 문자열로 지울 수 있다. 보존이 "아무것도 못 지운다"가 되면 안 된다.
* **가능시간 변경은 원장에 남는다**: ``schedule.as_visit.availability`` 는 보존 결함을 고친
  **뒤에** 화이트리스트에 넣었다 — 그 전에 넣었으면 저장 1회마다 허위 '지움' 행이 쌓였다.
"""

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderFieldChange, User


# --------------------------------------------------------------------------
# 픽스처 (tests/domains/test_audit_gap_flat_columns.py 와 같은 패턴)
# --------------------------------------------------------------------------
def _login(client, username, role="ADMIN", team="CS"):
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=f"{username}-name",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = username
        sess["role"] = role
    return user.id


def _as_visit_block():
    return {
        "date": "2026-09-10",
        "time": "14:00",
        "availability": {"days": "weekday", "time": "am"},
    }


def _sd_with_as_visit(**overrides):
    """AS 방문 일정이 실린 저장값(서버에 이미 있는 상태)."""
    sd = {
        "entity_type": "order_structured",
        "workflow": {"stage": "RECEIVED"},
        "parties": {"customer": {"name": "홍길동", "phone": "010-1234-5678"}},
        "site": {"address_full": "서울 테헤란로 1", "address_main": "서울 테헤란로 1"},
        "items": [{"product_name": "붙박이장", "price": 0}],
        "flags": {"urgent": False, "urgent_reason": "", "factory2": False},
        "schedule": {
            "measurement": {"date": "2026-09-01", "time": "10:00"},
            "construction": {"date": "2026-09-05", "time": "09:00"},
            "as_visit": _as_visit_block(),
        },
    }
    sd.update(overrides)
    return sd


def _form_sd(measurement=None, construction=None):
    """PC 폼이 실제로 조립해 보내는 모양 — ``as_visit`` 이 **없다**."""
    sd = _sd_with_as_visit()
    sd["schedule"] = {
        "measurement": measurement or {"date": "2026-09-01", "time": "10:00"},
        "construction": construction or {"date": "2026-09-05", "time": "09:00"},
    }
    return sd


def _create_order(**cols):
    sd = cols.pop("structured_data", None)
    order = Order(
        received_date="2026-08-26",
        customer_name="홍길동",
        phone="010-1234-5678",
        address="서울 테헤란로 1",
        product="붙박이장",
        status="RECEIVED",
        is_erp_order=True,
        structured_data=sd if sd is not None else _sd_with_as_visit(),
    )
    for key, value in cols.items():
        setattr(order, key, value)
    db_session.add(order)
    db_session.commit()
    return order.id


def _fresh(oid):
    db_session.expire_all()
    return db_session.get(Order, oid)


def _ledger(oid, path=None):
    db_session.expire_all()
    query = db_session.query(OrderFieldChange).filter(OrderFieldChange.order_id == oid)
    if path is not None:
        query = query.filter(OrderFieldChange.path == path)
    return query.order_by(OrderFieldChange.id).all()


def _put(client, oid, sd):
    return client.put(f"/api/orders/{oid}/structured", json={"structured_data": sd})


# --------------------------------------------------------------------------
# 1. 보존 — 폼이 안 보내는 as_visit 은 살아남는다
# --------------------------------------------------------------------------
def test_form_save_preserves_as_visit_block(client):
    """폼이 렌더하지 않는 ``schedule.as_visit`` 은 저장을 거쳐도 사라지지 않는다."""
    oid = _create_order()
    _login(client, "gap-asvisit-keep")

    res = _put(client, oid, _form_sd())

    assert res.status_code == 200, res.get_data(as_text=True)
    schedule = _fresh(oid).structured_data["schedule"]
    assert schedule.get("as_visit") == _as_visit_block(), "AS 방문 일정이 저장 한 번에 증발했다"


def test_form_save_does_not_leave_phantom_clear_rows(client):
    """보존되므로 ``as_visit`` 경로에 허위 '지움' 행이 생기지 않는다."""
    oid = _create_order()
    _login(client, "gap-asvisit-noise")

    assert _put(client, oid, _form_sd()).status_code == 200

    for path in (
        "schedule.as_visit.date",
        "schedule.as_visit.time",
        "schedule.as_visit.availability",
    ):
        assert _ledger(oid, path) == [], f"{path} 에 허위 행이 쌓였다"


# --------------------------------------------------------------------------
# 2. 보존이 "아무것도 못 지운다"가 되면 안 된다
# --------------------------------------------------------------------------
def test_preservation_does_not_block_clearing_measurement_date(client):
    """폼이 항상 보내는 실측일은 빈 문자열로 지울 수 있다."""
    oid = _create_order()
    _login(client, "gap-asvisit-clear")

    res = _put(client, oid, _form_sd(measurement={"date": "", "time": ""}))

    assert res.status_code == 200, res.get_data(as_text=True)
    schedule = _fresh(oid).structured_data["schedule"]
    assert not schedule["measurement"].get("date")
    assert not schedule["measurement"].get("time")
    # 지운 사실은 원장에 남아야 한다(보존이 기록까지 삼키면 안 된다).
    assert len(_ledger(oid, "schedule.measurement.date")) == 1
    # 그러면서 as_visit 은 여전히 살아 있다.
    assert schedule.get("as_visit") == _as_visit_block()


# --------------------------------------------------------------------------
# 3. 가능시간 변경은 원장에 남는다
# --------------------------------------------------------------------------
def test_as_visit_availability_change_lands_in_ledger(client):
    """가능시간대를 바꾸면 ``schedule.as_visit.availability`` 로 남는다."""
    oid = _create_order()
    _login(client, "gap-asvisit-change")

    changed = _sd_with_as_visit()
    changed["schedule"]["as_visit"]["availability"] = {"days": "weekend", "time": "pm"}
    res = _put(client, oid, changed)

    assert res.status_code == 200, res.get_data(as_text=True)
    # 저장이 실제로 반영됐는지 먼저 본다 — 요청이 죽어도 "행 없음"은 공짜로 통과한다.
    stored = _fresh(oid).structured_data["schedule"]["as_visit"]["availability"]
    assert stored == {"days": "weekend", "time": "pm"}

    rows = _ledger(oid, "schedule.as_visit.availability")
    assert len(rows) == 1
    assert rows[0].before_value != rows[0].after_value


def test_as_visit_availability_unchanged_save_records_no_row(client):
    """같은 가능시간으로 저장하면 행이 생기지 않는다."""
    oid = _create_order()
    _login(client, "gap-asvisit-noop")

    assert _put(client, oid, _sd_with_as_visit()).status_code == 200

    assert _ledger(oid, "schedule.as_visit.availability") == []
