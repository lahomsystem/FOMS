"""B1 통화 결과 기록 API 계약 테스트 (POST /api/orders/<id>/call-log).

앱 요청이 teardown에서 세션을 close → 테스트가 만든 ORM 인스턴스는 detach된다.
따라서 요청 전 정수 id만 확보하고, 요청 후 db_session.remove()로 세션을 리셋한 뒤
새 쿼리로 결과를 검증한다.
"""

from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, OrderEvent, User


def _login(client, *, username, role, team):
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
    uid = user.id
    with client.session_transaction() as sess:
        sess["user_id"] = uid
        sess["username"] = username
        sess["role"] = role
    return uid


def _create_order(*, status="RECEIVED", structured_data=None):
    order = Order(
        received_date="2026-04-07",
        customer_name="통화 대상",
        phone="010-1234-5678",
        address="Seoul",
        product="Wardrobe",
        status=status,
        manager_name="Alice",
        is_erp_order=True,
        structured_data=structured_data if structured_data is not None else {"workflow": {"stage": status}},
    )
    db_session.add(order)
    db_session.commit()
    oid = order.id
    return oid


def _fresh_order(oid):
    db_session.remove()
    return db_session.query(Order).filter_by(id=oid).first()


def test_call_log_saves_and_appends(client, app):
    """정상 저장 → 200, sd['calls'] append, OrderEvent(CALL_LOGGED) 기록."""
    _login(client, username="cs-editor", role="STAFF", team="CS")
    oid = _create_order()

    resp = client.post(
        f"/api/orders/{oid}/call-log",
        json={"result": "connected", "memo": "고객 확인함"},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["data"]["calls_count"] == 1

    refreshed = _fresh_order(oid)
    calls = refreshed.structured_data["calls"]
    assert len(calls) == 1
    assert calls[0]["result"] == "connected"
    assert calls[0]["memo"] == "고객 확인함"
    assert calls[0]["by_name"] == "cs-editor-name"
    assert "at" in calls[0]

    events = db_session.query(OrderEvent).filter_by(order_id=oid, event_type="CALL_LOGGED").all()
    assert len(events) == 1
    assert events[0].payload["result"] == "connected"
    assert events[0].payload["memo_len"] == len("고객 확인함")


def test_call_log_caps_at_50(client, app):
    """cap 50 초과 시 앞에서 절단되어 최신 50건만 유지."""
    _login(client, username="cs-cap", role="STAFF", team="CS")
    seed_calls = [
        {"at": "x", "by": 0, "by_name": "seed", "result": "connected", "memo": str(i)}
        for i in range(50)
    ]
    oid = _create_order(structured_data={"workflow": {"stage": "RECEIVED"}, "calls": seed_calls})

    resp = client.post(f"/api/orders/{oid}/call-log", json={"result": "no_answer"})
    assert resp.status_code == 200

    refreshed = _fresh_order(oid)
    calls = refreshed.structured_data["calls"]
    assert len(calls) == 50
    assert calls[-1]["result"] == "no_answer"
    # 가장 오래된(memo="0") 항목이 절단됨
    assert calls[0]["memo"] == "1"


def test_call_log_updates_measurement_date(client, app):
    """measurement_date 전달 → schedule.measurement.date 갱신 + MEASUREMENT_DATE_CHANGED."""
    _login(client, username="cs-meas", role="STAFF", team="CS")
    oid = _create_order()

    resp = client.post(
        f"/api/orders/{oid}/call-log",
        json={"result": "schedule_confirmed", "measurement_date": "2026-05-20"},
    )
    assert resp.status_code == 200

    refreshed = _fresh_order(oid)
    assert refreshed.structured_data["schedule"]["measurement"]["date"] == "2026-05-20"

    meas_events = (
        db_session.query(OrderEvent)
        .filter_by(order_id=oid, event_type="MEASUREMENT_DATE_CHANGED")
        .all()
    )
    assert len(meas_events) == 1
    assert meas_events[0].payload["to"] == "2026-05-20"


def test_call_log_forbidden_for_ineligible_team(client, app):
    """자격 없는 팀(DRAWING) → 403, 저장/이벤트 없음."""
    _login(client, username="drawing-user", role="STAFF", team="DRAWING")
    oid = _create_order()

    resp = client.post(f"/api/orders/{oid}/call-log", json={"result": "connected"})
    assert resp.status_code == 403

    refreshed = _fresh_order(oid)
    assert "calls" not in (refreshed.structured_data or {})
    assert db_session.query(OrderEvent).filter_by(order_id=oid).count() == 0


def test_call_log_rejects_invalid_payload(client, app):
    """잘못된 result → 400, 저장 없음."""
    _login(client, username="cs-bad", role="STAFF", team="CS")
    oid = _create_order()

    resp = client.post(f"/api/orders/{oid}/call-log", json={"result": "bogus"})
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False

    refreshed = _fresh_order(oid)
    assert "calls" not in (refreshed.structured_data or {})


def test_call_log_rejects_bad_measurement_date(client, app):
    """잘못된 measurement_date 형식 → 400."""
    _login(client, username="cs-baddate", role="STAFF", team="CS")
    oid = _create_order()

    resp = client.post(
        f"/api/orders/{oid}/call-log",
        json={"result": "connected", "measurement_date": "2026/05/20"},
    )
    assert resp.status_code == 400
    assert resp.get_json()["success"] is False
