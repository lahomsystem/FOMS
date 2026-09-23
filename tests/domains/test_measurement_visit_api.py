"""실측 방문 체크 API 계약 (POST /api/orders/<id>/measurement-visit, MEASUREMENT-VISIT-01).

앱 요청이 teardown 에서 세션을 close → 테스트가 만든 ORM 인스턴스는 detach 된다. 그래서
요청 전 정수 id 만 들고, 요청 뒤 ``db_session.remove()`` 로 세션을 비운 다음 새로 읽는다
(``test_call_log_api.py`` 와 같은 방식).
"""

import copy

from sqlalchemy import update
from werkzeug.security import generate_password_hash

from db import db_session
from foms.api.erp_orders_structured import (
    _OPERATIONAL_TOP_LEVEL_KEYS,
    _preserve_operational_structured_state,
)
from foms.services.orders.structured_form_projection import project_structured_form
from models import Order, OrderEvent, SecurityLog, User

DATE = "2026-09-23"
MARKED = "MEASUREMENT_VISIT_MARKED"
UNMARKED = "MEASUREMENT_VISIT_UNMARKED"


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


def _base_sd():
    return {
        "workflow": {"stage": "MEASURE"},
        "quests": [{"stage": "MEASURE", "status": "OPEN", "team": "SALES"}],
        "schedule": {"measurement": {"date": DATE, "time": "14:00"}},
    }


def _create_order(*, structured_data=None):
    order = Order(
        received_date="2026-09-20",
        customer_name="실측 대상",
        phone="010-1234-5678",
        address="Seoul",
        product="Wardrobe",
        status="MEASURE",
        manager_name="최진호",
        is_erp_order=True,
        measurement_completed=False,
        structured_data=structured_data if structured_data is not None else _base_sd(),
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _fresh_order(oid):
    db_session.remove()
    return db_session.query(Order).filter_by(id=oid).first()


def _events(oid, event_type):
    return db_session.query(OrderEvent).filter_by(order_id=oid, event_type=event_type).count()


def _post(client, oid, payload, headers=None):
    return client.post(f"/api/orders/{oid}/measurement-visit", json=payload, headers=headers or {})


def _sales(client, name="sales-visit"):
    return _login(client, username=name, role="STAFF", team="SALES")


def test_viewer_is_forbidden_and_nothing_changes(client, app):
    _login(client, username="viewer-visit", role="VIEWER", team="SALES")
    oid = _create_order()
    before = _fresh_order(oid).mutation_version

    resp = _post(client, oid, {"date": DATE, "done": True})
    assert resp.status_code == 403
    body = resp.get_json()
    assert body["success"] is False
    assert body["data"] is None

    order = _fresh_order(oid)
    assert "measurement_visits" not in (order.structured_data or {})
    assert order.mutation_version == before
    assert db_session.query(OrderEvent).filter(
        OrderEvent.order_id == oid, OrderEvent.event_type.in_((MARKED, UNMARKED))
    ).count() == 0


def test_mark_writes_entry_event_version_and_audit(client, app):
    uid = _sales(client)
    oid = _create_order()
    before = _fresh_order(oid).mutation_version

    resp = _post(client, oid, {"date": DATE, "done": True, "stage": "DRAWING"})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["error"] is None
    data = body["data"]
    assert data["date"] == DATE and data["done"] is True and data["changed"] is True
    assert data["by_name"] == "sales-visit-name"
    assert data["at"]
    assert data["mutation_receipt"]

    order = _fresh_order(oid)
    entry = order.structured_data["measurement_visits"][DATE]
    assert entry["by_name"] == "sales-visit-name"
    assert entry["by_user_id"] == uid
    assert entry["at"] == data["at"]
    assert entry["at"].endswith("+09:00")
    assert order.mutation_version == before + 1
    assert _events(oid, MARKED) == 1
    ev = db_session.query(OrderEvent).filter_by(order_id=oid, event_type=MARKED).first()
    assert ev.payload == {"date": DATE}
    assert ev.created_by_user_id == uid
    logs = db_session.query(SecurityLog).filter_by(
        action="ORDER_MEASUREMENT_VISIT_MARKED", target_id=oid
    ).all()
    assert len(logs) == 1
    assert logs[0].target_type == "order"


def test_repeat_same_state_is_noop(client, app):
    _sales(client)
    oid = _create_order()
    assert _post(client, oid, {"date": DATE, "done": True}).status_code == 200
    first = _fresh_order(oid)
    version, at = first.mutation_version, first.structured_data["measurement_visits"][DATE]["at"]

    resp = _post(client, oid, {"date": DATE, "done": True})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["changed"] is False
    assert data["mutation_receipt"] is None
    assert data["at"] == at
    assert data["by_name"] == "sales-visit-name"

    order = _fresh_order(oid)
    assert order.mutation_version == version
    assert _events(oid, MARKED) == 1

    # 체크 안 된 날짜를 해제해도 no-op 이다.
    resp = _post(client, oid, {"date": "2026-09-24", "done": False})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["changed"] is False and data["at"] is None and data["by_name"] is None
    assert _fresh_order(oid).mutation_version == version
    assert _events(oid, UNMARKED) == 0


def test_unmark_removes_key_and_records_event(client, app):
    _sales(client)
    oid = _create_order()
    assert _post(client, oid, {"date": DATE, "done": True}).status_code == 200
    version = _fresh_order(oid).mutation_version

    resp = _post(client, oid, {"date": DATE, "done": False})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["done"] is False and data["changed"] is True
    assert data["at"] is None and data["by_name"] is None

    order = _fresh_order(oid)
    assert DATE not in order.structured_data["measurement_visits"]
    assert order.mutation_version == version + 1
    assert _events(oid, UNMARKED) == 1
    assert db_session.query(SecurityLog).filter_by(
        action="ORDER_MEASUREMENT_VISIT_UNMARKED", target_id=oid
    ).count() == 1


def test_stage_quests_and_measurement_completed_untouched(client, app):
    _sales(client)
    oid = _create_order()
    before = copy.deepcopy(_fresh_order(oid).structured_data)

    assert _post(client, oid, {"date": DATE, "done": True, "measurement_completed": True}).status_code == 200

    order = _fresh_order(oid)
    sd = order.structured_data
    assert order.measurement_completed is False
    assert order.status == "MEASURE"
    assert sd["workflow"] == before["workflow"]
    assert sd["quests"] == before["quests"]
    assert sd["schedule"] == before["schedule"]
    assert set(sd) - set(before) == {"measurement_visits"}
    assert _events(oid, "MEASUREMENT_COMPLETED") == 0


def test_idempotency_key_same_body_writes_nothing_again(client, app):
    _sales(client)
    oid = _create_order()
    key = {"Idempotency-Key": "7b1f7a52-2b1e-4b1f-9d1c-1a2b3c4d5e6f"}
    assert _post(client, oid, {"date": DATE, "done": True}, key).status_code == 200
    version = _fresh_order(oid).mutation_version

    resp = _post(client, oid, {"date": DATE, "done": True}, key)
    assert resp.status_code == 200
    assert resp.get_json()["data"]["changed"] is False
    assert _fresh_order(oid).mutation_version == version
    assert _events(oid, MARKED) == 1


def test_idempotency_key_reused_with_flipped_body_is_rejected(client, app):
    _sales(client)
    oid = _create_order()
    key = {"Idempotency-Key": "8c2e8b63-3c2f-4c2e-8e2d-2b3c4d5e6f70"}
    assert _post(client, oid, {"date": DATE, "done": True}, key).status_code == 200
    version = _fresh_order(oid).mutation_version

    resp = _post(client, oid, {"date": DATE, "done": False}, key)
    assert resp.status_code != 200
    body = resp.get_json()
    assert body["success"] is False
    assert body["data"] is None

    order = _fresh_order(oid)
    assert DATE in order.structured_data["measurement_visits"]
    assert order.mutation_version == version
    assert _events(oid, UNMARKED) == 0


def test_if_match_mismatch_is_409(client, app):
    _sales(client)
    oid = _create_order()
    version = _fresh_order(oid).mutation_version

    resp = _post(client, oid, {"date": DATE, "done": True}, {"If-Match": str(version + 5)})
    assert resp.status_code == 409
    assert resp.get_json()["success"] is False
    order = _fresh_order(oid)
    assert "measurement_visits" not in order.structured_data
    assert order.mutation_version == version

    resp = _post(client, oid, {"date": DATE, "done": True}, {"If-Match": str(version)})
    assert resp.status_code == 200


def test_bad_if_match_format_is_400(client, app):
    _sales(client)
    oid = _create_order()
    resp = _post(client, oid, {"date": DATE, "done": True}, {"If-Match": "abc"})
    assert resp.status_code == 400


def test_invalid_inputs_and_missing_order(client, app):
    _sales(client)
    oid = _create_order()
    for payload in (
        {"date": "2026/09/23", "done": True},
        {"date": "2026-02-30", "done": True},
        {"done": True},
        {"date": DATE, "done": "true"},
        {"date": DATE, "done": 1},
        {"date": DATE},
    ):
        resp = _post(client, oid, payload)
        assert resp.status_code == 400, payload
        body = resp.get_json()
        assert body["success"] is False and body["data"] is None and body["error"]
    assert "measurement_visits" not in _fresh_order(oid).structured_data

    resp = _post(client, 987654321, {"date": DATE, "done": True})
    assert resp.status_code == 404
    assert resp.get_json() == {"success": False, "data": None, "error": "주문을 찾을 수 없습니다."}


def test_full_form_save_preserves_measurement_visits(client, app):
    """폼 전체 저장이 서버 소유 키를 지우지 않는다(2026-09-10 drawing_wizard 사고와 같은 축)."""
    assert "measurement_visits" in _OPERATIONAL_TOP_LEVEL_KEYS

    _sales(client)
    oid = _create_order()
    assert _post(client, oid, {"date": DATE, "done": True}).status_code == 200
    old = copy.deepcopy(_fresh_order(oid).structured_data)
    expected = copy.deepcopy(old["measurement_visits"])

    incoming = {
        "items": [{"price": 1000}],
        "parties": {"customer": {"name": "실측 대상"}},
        "site": {},
        "workflow": {},
        "schedule": {},
        "notes": "",
        "flags": {},
        "payment": {},
        "shipment": {},
        "entity_type": "order_structured",
    }
    _preserve_operational_structured_state(old, incoming)
    project_structured_form(old, incoming)
    assert incoming.get("measurement_visits") == expected


def test_stale_identity_map_does_not_lose_other_structured_data_write(client, app):
    """잠금 전에 읽어 둔 낡은 주문 객체로 되쓰지 않는다(lost update 회귀).

    같은 세션 identity map 에 옛 structured_data 가 남은 상태에서, 다른 경로가 다른 키를 바꿔
    커밋했다고 친다(ORM 동기화 없는 UPDATE). API 는 잠금 아래 최신 값에 체크를 얹어야 한다.
    """
    _sales(client)
    oid = _create_order()
    db_session.remove()
    stale = db_session.query(Order).filter_by(id=oid).first()
    newer = copy.deepcopy(stale.structured_data)
    newer["calls"] = [{"result": "통화", "memo": "다른 창에서 저장"}]
    db_session.execute(
        update(Order)
        .where(Order.id == oid)
        .values(structured_data=newer)
        .execution_options(synchronize_session=False)
    )
    assert "calls" not in stale.structured_data  # identity map 은 아직 낡은 값

    resp = _post(client, oid, {"date": DATE, "done": True})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["changed"] is True

    sd = _fresh_order(oid).structured_data
    assert sd["calls"] == [{"result": "통화", "memo": "다른 창에서 저장"}]
    assert DATE in sd["measurement_visits"]


def test_race_to_same_state_under_lock_writes_nothing(client, app, monkeypatch):
    """잠금 전 판정은 '바뀜'인데 잠금 아래에서 보니 이미 같은 상태(경합) → 쓰기·버전·이벤트 0."""
    import foms.api.orders.measurement_visit as mv

    _sales(client)
    oid = _create_order()
    assert _post(client, oid, {"date": DATE, "done": True}).status_code == 200
    version = _fresh_order(oid).mutation_version

    # 사전 판정만 속인다(다른 요청이 잠금 직전에 먼저 체크한 상황).
    monkeypatch.setattr(mv, "is_visit_marked", lambda sd, d: False)
    resp = _post(client, oid, {"date": DATE, "done": True})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["changed"] is False
    assert data["mutation_receipt"] is None
    assert data["done"] is True and data["at"]

    assert _fresh_order(oid).mutation_version == version
    assert _events(oid, MARKED) == 1


def test_if_match_is_checked_before_noop(client, app):
    """If-Match 가 먼저다: 이미 같은 상태여도 버전이 어긋나면 409(잠금 경로와 같은 순서)."""
    _sales(client)
    oid = _create_order()
    assert _post(client, oid, {"date": DATE, "done": True}).status_code == 200
    version = _fresh_order(oid).mutation_version

    resp = _post(client, oid, {"date": DATE, "done": True}, {"If-Match": str(version - 1)})
    assert resp.status_code == 409
    assert _fresh_order(oid).mutation_version == version

    resp = _post(client, oid, {"date": DATE, "done": True}, {"If-Match": str(version)})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["changed"] is False


def test_replay_reports_current_state_not_request_value(client, app):
    """옛 키 재요청(replay) 응답의 done 은 지금 저장된 상태를 따른다."""
    _sales(client)
    oid = _create_order()
    key_a = {"Idempotency-Key": "9d3f9c74-4d3a-4d3f-8f3e-3c4d5e6f7081"}
    key_b = {"Idempotency-Key": "ae4a0d85-5e4b-4e4a-9a4f-4d5e6f708192"}
    assert _post(client, oid, {"date": DATE, "done": True}, key_a).status_code == 200
    assert _post(client, oid, {"date": DATE, "done": False}, key_b).status_code == 200
    version = _fresh_order(oid).mutation_version

    resp = _post(client, oid, {"date": DATE, "done": True}, key_a)
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["done"] is False
    assert data["at"] is None
    assert _fresh_order(oid).mutation_version == version
    assert _events(oid, MARKED) == 1
